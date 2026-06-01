from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from typing import Deque, Protocol

from .dialogflow import DialogflowClient, IntentResult
from .knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)


class NlpClient(Protocol):
    def detect_intent(self, session: str, text: str) -> IntentResult: ...


def make_nlp_client_from_env() -> NlpClient:
    """Pick the NLP backend based on CHATBOT_NLP_BACKEND.

    "gemma"  → GemmaClient (local Ollama, intent classifier only).
    "gemini" → GeminiClient (Google AI, direct-reply generation).
    Anything else (or import failure) → DialogflowClient stub.
    """
    backend = os.environ.get("CHATBOT_NLP_BACKEND", "dialogflow").strip().lower()
    if backend == "gemma":
        try:
            from .gemma import GemmaClient
            return GemmaClient()
        except Exception as exc:
            log.warning("Gemma backend requested but failed to initialise: %s", exc)
    elif backend == "gemini":
        try:
            from .gemini import GeminiClient
            return GeminiClient()
        except Exception as exc:
            log.warning("Gemini backend requested but failed to initialise: %s", exc)
    return DialogflowClient()


class ChatbotEngine:
    """Orchestrates intent detection, KB lookup, context, and fallback."""

    def __init__(
        self,
        nlp: NlpClient | None = None,
        kb: KnowledgeBase | None = None,
        history_size: int = 6,
        confidence_threshold: float | None = None,
    ):
        self.nlp = nlp or make_nlp_client_from_env()
        self.kb = kb or KnowledgeBase.load_default()
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.environ.get("CHATBOT_CONFIDENCE_THRESHOLD", "0.6"))
        )
        self._history: dict[str, Deque[tuple[str, str]]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )

    def handle(self, user_id: str, text: str, group_id: str | None = None) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        session_key = group_id or user_id

        # Direct-reply backends (e.g. Gemini) produce the user-facing answer
        # themselves; intent-classifier backends (Dialogflow, Gemma) only
        # label the message and we serve the canonical answer from the KB.
        if hasattr(self.nlp, "generate_reply"):
            answer = self.nlp.generate_reply(
                session=session_key,
                text=text,
                history=list(self._history[session_key]),
            )
            if not answer:
                answer = self._fallback()
        else:
            result: IntentResult = self.nlp.detect_intent(session=session_key, text=text)
            answer = self._answer_for(result)

        self._history[session_key].append((text, answer))
        return answer

    def _answer_for(self, result: IntentResult) -> str:
        if not result.intent or result.confidence < self.confidence_threshold:
            return self._fallback()

        kb_answer = self.kb.answer_for_intent(result.intent)
        if kb_answer:
            return kb_answer

        if result.fulfillment_text:
            return result.fulfillment_text

        return self._fallback()

    def history(self, session_key: str) -> list[tuple[str, str]]:
        return list(self._history.get(session_key, ()))

    @staticmethod
    def _fallback() -> str:
        contact = os.environ.get(
            "CHATBOT_FALLBACK_CONTACT",
            "I'm not sure about that one yet. Please contact the relevant office for help.",
        )
        return (
            "I don't have a confident answer for that question. "
            f"{contact}"
        )
