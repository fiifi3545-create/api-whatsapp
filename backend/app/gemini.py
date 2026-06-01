"""Google Gemini direct-reply client.

Calls the Gemini REST API to generate full chat answers (unlike GemmaClient
which only classifies intents). Activated via `CHATBOT_NLP_BACKEND=gemini`
plus `GEMINI_API_KEY` in the environment.

The chatbot engine treats any backend that exposes `generate_reply` as a
direct-answer backend and skips the KB lookup. Degrades to an empty reply on
any failure so the chatbot's fallback path covers the user — the webhook
never 500s.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 20  # seconds

SYSTEM_INSTRUCTION = (
    "You are a friendly support chatbot for university students. "
    "Replies are read on WhatsApp, so keep them short and clear — under "
    "100 words unless the student explicitly asks for more detail. "
    "You help with study questions, exams, registration, fees, library "
    "use, and general campus life. "
    "If you don't know something specific to the student's school "
    "(exact dates, office phone numbers, room numbers, fee amounts), "
    "say so honestly and suggest contacting the Student Affairs office "
    "rather than guessing. Never invent dates, names, or contact details."
)


class GeminiClient:
    """Generates full replies via the Gemini REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        system_instruction: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self.api_base = (
            api_base or os.environ.get("GEMINI_API_BASE") or DEFAULT_API_BASE
        ).rstrip("/")
        self.timeout = timeout
        self.system_instruction = system_instruction or os.environ.get(
            "GEMINI_SYSTEM_INSTRUCTION", SYSTEM_INSTRUCTION
        )

    def generate_reply(
        self,
        session: str,  # noqa: ARG002 — interface parity; conversation state lives in the engine
        text: str,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        if not self.api_key:
            log.warning("GEMINI_API_KEY not set; Gemini backend returning empty reply")
            return ""

        contents: list[dict] = []
        for user_text, bot_text in (history or [])[-4:]:
            if user_text:
                contents.append({"role": "user", "parts": [{"text": user_text}]})
            if bot_text:
                contents.append({"role": "model", "parts": [{"text": bot_text}]})
        contents.append({"role": "user", "parts": [{"text": text}]})

        url = f"{self.api_base}/models/{self.model}:generateContent"
        body = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": self.system_instruction}]},
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 400,
            },
        }

        try:
            resp = requests.post(
                url,
                params={"key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            log.warning("Gemini API call failed: %s", exc)
            return ""
        except ValueError as exc:
            log.warning("Gemini returned non-JSON body: %s", exc)
            return ""

        return self._extract_text(payload)

    @staticmethod
    def _extract_text(payload: dict) -> str:
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not candidates:
            log.warning("Gemini returned no candidates: %r", payload)
            return ""

        first = candidates[0]
        if not isinstance(first, dict):
            return ""

        content = first.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if not parts:
            return ""

        chunks = []
        for part in parts:
            if isinstance(part, dict):
                value = part.get("text")
                if isinstance(value, str):
                    chunks.append(value)
        return "".join(chunks).strip()
