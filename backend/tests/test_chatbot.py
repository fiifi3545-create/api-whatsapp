import pytest

from app.chatbot import ChatbotEngine
from app.dialogflow import DialogflowClient


@pytest.fixture
def engine():
    # Pin to the Dialogflow stub so these tests stay deterministic regardless
    # of what CHATBOT_NLP_BACKEND happens to be set to in the dev .env.
    return ChatbotEngine(nlp=DialogflowClient())


def test_known_intent_returns_kb_answer(engine):
    reply = engine.handle(user_id="u1", text="when is the exam timetable out?")
    assert "Examination timetable" in reply or "exam" in reply.lower()


def test_unknown_intent_falls_back(engine):
    reply = engine.handle(user_id="u1", text="completely unrelated topic xyzzy")
    assert "don't have a confident answer" in reply.lower() or "confident answer" in reply.lower()


def test_history_is_per_session(engine):
    engine.handle(user_id="u1", text="library hours?")
    engine.handle(user_id="u1", text="registration?")
    assert len(engine.history("u1")) == 2
    assert engine.history("u2") == []


def test_empty_message_returns_empty(engine):
    assert engine.handle(user_id="u1", text="   ") == ""
