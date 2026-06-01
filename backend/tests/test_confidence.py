from app.chatbot import ChatbotEngine
from app.dialogflow import DialogflowClient, IntentResult


class _FakeNLP(DialogflowClient):
    def __init__(self, result: IntentResult):
        self._result = result

    def detect_intent(self, session: str, text: str) -> IntentResult:
        return self._result


def _engine(result: IntentResult, threshold: float = 0.6) -> ChatbotEngine:
    return ChatbotEngine(nlp=_FakeNLP(result), confidence_threshold=threshold)


def test_high_confidence_known_intent_returns_kb_answer():
    engine = _engine(IntentResult(intent="library.hours", confidence=0.9))
    reply = engine.handle("u1", "when is the library open?")
    assert "library" in reply.lower()


def test_low_confidence_falls_back_even_when_intent_matches_kb():
    engine = _engine(IntentResult(intent="library.hours", confidence=0.3))
    reply = engine.handle("u1", "when is the library open?")
    assert "confident answer" in reply.lower()


def test_high_confidence_unknown_intent_uses_dialogflow_fulfillment():
    engine = _engine(
        IntentResult(
            intent="some.new.intent",
            confidence=0.95,
            fulfillment_text="Here is the answer from Dialogflow.",
        )
    )
    reply = engine.handle("u1", "anything")
    assert reply == "Here is the answer from Dialogflow."


def test_threshold_boundary_is_inclusive_at_threshold():
    engine = _engine(IntentResult(intent="library.hours", confidence=0.6), threshold=0.6)
    reply = engine.handle("u1", "library?")
    assert "library" in reply.lower()


def test_empty_intent_always_falls_back_regardless_of_confidence():
    engine = _engine(IntentResult(intent="", confidence=0.99))
    reply = engine.handle("u1", "unparseable noise")
    assert "confident answer" in reply.lower()
