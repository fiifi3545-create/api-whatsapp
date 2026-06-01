from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class IntentResult:
    intent: str
    confidence: float
    fulfillment_text: str = ""


class DialogflowClient:
    """Thin wrapper around Dialogflow ES.

    Degrades to a no-op stub when GOOGLE_APPLICATION_CREDENTIALS or
    DIALOGFLOW_PROJECT_ID are unset, so the app boots locally without GCP.
    """

    def __init__(self, project_id: str | None = None, language_code: str = "en"):
        self.project_id = project_id or os.environ.get("DIALOGFLOW_PROJECT_ID", "")
        self.language_code = language_code or os.environ.get("DIALOGFLOW_LANGUAGE_CODE", "en")
        self._sessions_client = None

        if self.project_id and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                from google.cloud import dialogflow

                self._sessions_client = dialogflow.SessionsClient()
                self._dialogflow = dialogflow
            except Exception as exc:
                log.warning("Dialogflow init failed, falling back to stub: %s", exc)

    def detect_intent(self, session: str, text: str) -> IntentResult:
        if self._sessions_client is None:
            return self._stub(text)

        session_path = self._sessions_client.session_path(self.project_id, session)
        text_input = self._dialogflow.TextInput(text=text, language_code=self.language_code)
        query_input = self._dialogflow.QueryInput(text=text_input)

        response = self._sessions_client.detect_intent(
            request={"session": session_path, "query_input": query_input}
        )
        result = response.query_result
        return IntentResult(
            intent=result.intent.display_name if result.intent else "",
            confidence=float(result.intent_detection_confidence),
            fulfillment_text=result.fulfillment_text,
        )

    @staticmethod
    def _stub(text: str) -> IntentResult:
        lowered = text.lower()
        if "exam" in lowered:
            return IntentResult(intent="exam.schedule", confidence=0.7)
        if "register" in lowered or "registration" in lowered:
            return IntentResult(intent="registration.info", confidence=0.7)
        if "library" in lowered:
            return IntentResult(intent="library.hours", confidence=0.7)
        if "fee" in lowered or "tuition" in lowered or "payment" in lowered:
            return IntentResult(intent="fees.payment", confidence=0.7)
        if "transcript" in lowered:
            return IntentResult(intent="transcripts.request", confidence=0.7)
        return IntentResult(intent="", confidence=0.0)
