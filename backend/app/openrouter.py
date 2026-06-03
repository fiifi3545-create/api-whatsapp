"""OpenRouter direct-reply client (OpenAI-compatible).

OpenRouter (https://openrouter.ai) is an OpenAI-compatible gateway that can
route to OpenAI, Anthropic, Google, Meta and many other models behind one
API key (keys look like ``sk-or-v1-...``). This client calls the
``/chat/completions`` endpoint to generate full chat answers — unlike the
intent-classifier backends (Dialogflow, Gemma), it produces the user-facing
reply directly.

Activated via ``CHATBOT_NLP_BACKEND=openrouter`` (alias: ``openai``) plus
``OPENROUTER_API_KEY`` in the environment. The chatbot engine treats any
backend exposing ``generate_reply`` as a direct-answer backend and skips the
KB lookup. Degrades to an empty reply on any failure so the chatbot's
fallback path covers the user — the webhook never 500s.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 30  # seconds — OpenRouter can be slower than direct providers

SYSTEM_INSTRUCTION = (
    "You are a friendly support chatbot for university students. "
    "Replies may be read on WhatsApp, so keep them short and clear — under "
    "100 words unless the student explicitly asks for more detail. "
    "You help with study questions, exams, registration, fees, library "
    "use, and general campus life. "
    "If you don't know something specific to the student's school "
    "(exact dates, office phone numbers, room numbers, fee amounts), "
    "say so honestly and suggest contacting the Student Affairs office "
    "rather than guessing. Never invent dates, names, or contact details."
)


class OpenRouterClient:
    """Generates full replies via the OpenRouter chat-completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_base: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        system_instruction: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
        self.api_base = (
            api_base or os.environ.get("OPENROUTER_API_BASE") or DEFAULT_API_BASE
        ).rstrip("/")
        self.timeout = timeout
        self.system_instruction = system_instruction or os.environ.get(
            "OPENROUTER_SYSTEM_INSTRUCTION", SYSTEM_INSTRUCTION
        )

    def generate_reply(
        self,
        session: str,  # noqa: ARG002 — interface parity; conversation state lives in the engine
        text: str,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        if not self.api_key:
            log.warning(
                "OPENROUTER_API_KEY not set; OpenRouter backend returning empty reply"
            )
            return ""

        messages: list[dict] = [
            {"role": "system", "content": self.system_instruction}
        ]
        for user_text, bot_text in (history or [])[-4:]:
            if user_text:
                messages.append({"role": "user", "content": user_text})
            if bot_text:
                messages.append({"role": "assistant", "content": bot_text})
        messages.append({"role": "user", "content": text})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers OpenRouter uses for rankings; harmless
            # if the referrer isn't a real site.
            "HTTP-Referer": os.environ.get(
                "OPENROUTER_REFERRER", "https://student-chatbot-backend.onrender.com"
            ),
            "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "Student Chatbot"),
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 400,
        }

        try:
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            log.warning("OpenRouter API call failed: %s", exc)
            return ""
        except ValueError as exc:
            log.warning("OpenRouter returned non-JSON body: %s", exc)
            return ""

        return self._extract_text(payload)

    @staticmethod
    def _extract_text(payload: dict) -> str:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not choices:
            log.warning("OpenRouter returned no choices: %r", payload)
            return ""

        first = choices[0]
        if not isinstance(first, dict):
            return ""

        message = first.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip()
        # Some models return content as a list of parts.
        if isinstance(content, list):
            chunks = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ]
            return "".join(chunks).strip()
        return ""
