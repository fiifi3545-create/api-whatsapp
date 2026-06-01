"""Gemma (via Ollama) intent classifier.

Drop-in replacement for `DialogflowClient.detect_intent`: given a free-form
student question, returns one of the curated intent labels from the KB so the
chatbot can continue to serve the canonical answer from `faqs.json`. The LLM
never writes the user-facing answer — it only chooses the intent — which keeps
the thesis spec's "knowledge base as first-class data asset" intact and rules
out hallucinated fee deadlines / office names.

Communicates with a local Ollama server (`ollama run gemma3:4b`) over HTTP.
Degrades to a no-intent result on any failure so the chatbot's existing
fallback path takes over instead of 500-ing the webhook.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import requests

from .dialogflow import IntentResult

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:4b"
DEFAULT_TIMEOUT = 15  # seconds — Gemma 4B on CPU can be slow


@dataclass(frozen=True)
class IntentCatalogEntry:
    name: str
    examples: tuple[str, ...]


def load_catalog_from_file(
    path: Path | None = None,
) -> list[IntentCatalogEntry]:
    """Build the prompt's intent catalog from dialogflow_intents.json.

    Training phrases double as few-shot examples for the classifier — that's
    literally what they're for, no separate description field needed.
    """
    if path is None:
        path = (
            Path(__file__).resolve().parent.parent
            / "knowledge_base"
            / "dialogflow_intents.json"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        IntentCatalogEntry(
            name=intent["display_name"],
            examples=tuple(intent.get("training_phrases", [])),
        )
        for intent in data.get("intents", [])
    ]


def build_prompt(
    catalog: list[IntentCatalogEntry],
    text: str,
    history: list[tuple[str, str]] | None = None,
) -> str:
    """Construct the classifier prompt. Public for testability."""
    catalog_block = "\n".join(
        f"- {entry.name}: example questions: "
        + "; ".join(f'"{ex}"' for ex in entry.examples)
        for entry in catalog
    )

    history_block = ""
    if history:
        recent = history[-2:]  # last two turns of context, no more
        lines = []
        for user_text, bot_text in recent:
            lines.append(f"User: {user_text}")
            if bot_text:
                lines.append(f"Bot: {bot_text}")
        history_block = "Recent conversation (oldest first):\n" + "\n".join(lines) + "\n\n"

    intent_names = ", ".join(entry.name for entry in catalog)

    return (
        "You are an intent classifier for a university student support chatbot. "
        "Your only job is to pick the best matching intent label for the current "
        "student message. Do not write an answer. Do not invent new intent names.\n\n"
        f"Available intents:\n{catalog_block}\n\n"
        f"{history_block}"
        f"Current message: {text}\n\n"
        "Respond with JSON only, on a single line, in this exact shape:\n"
        f'{{"intent": "<one of: {intent_names}, or unknown>", "confidence": <number between 0 and 1>}}\n'
    )


class GemmaClient:
    """Talks to Ollama. Returns IntentResult so it's wire-compatible with DialogflowClient."""

    def __init__(
        self,
        catalog: list[IntentCatalogEntry] | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.catalog = catalog if catalog is not None else load_catalog_from_file()
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self._valid_intent_names = {entry.name for entry in self.catalog}

    def detect_intent(
        self,
        session: str,  # noqa: ARG002 — kept for interface parity with DialogflowClient
        text: str,
        history: list[tuple[str, str]] | None = None,
    ) -> IntentResult:
        prompt = build_prompt(self.catalog, text, history)

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.0},
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            log.warning("Ollama unreachable, falling back to no-intent: %s", exc)
            return IntentResult(intent="", confidence=0.0)

        raw_response = (payload.get("response") or "").strip()
        if not raw_response:
            log.warning("Ollama returned empty response; treating as no-intent")
            return IntentResult(intent="", confidence=0.0)

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            log.warning("Ollama returned non-JSON output: %r", raw_response[:200])
            return IntentResult(intent="", confidence=0.0)

        intent = (parsed.get("intent") or "").strip()
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        if intent in (None, "", "unknown"):
            return IntentResult(intent="", confidence=0.0)
        if intent not in self._valid_intent_names:
            # Model hallucinated an intent name. Reject it — fallback wins.
            log.warning("Ollama returned unknown intent %r; rejecting", intent)
            return IntentResult(intent="", confidence=0.0)

        return IntentResult(
            intent=intent,
            confidence=max(0.0, min(1.0, confidence)),
        )
