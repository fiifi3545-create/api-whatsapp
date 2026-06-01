import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.chatbot import make_nlp_client_from_env
from app.dialogflow import DialogflowClient
from app.gemma import (
    GemmaClient,
    IntentCatalogEntry,
    build_prompt,
    load_catalog_from_file,
)


CATALOG = [
    IntentCatalogEntry(name="library.hours", examples=("library hours", "when is the library open")),
    IntentCatalogEntry(name="exam.schedule", examples=("when is the exam", "exam timetable")),
]


def _fake_response(json_body: dict) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.status_code = 200
    r.json.return_value = json_body
    r.raise_for_status.return_value = None
    return r


# ----- prompt builder ----------------------------------------------------
def test_build_prompt_lists_intents_and_examples():
    prompt = build_prompt(CATALOG, text="library hours please")
    assert "library.hours" in prompt
    assert "exam.schedule" in prompt
    assert "library hours please" in prompt
    assert '"library hours"' in prompt
    assert "Respond with JSON only" in prompt


def test_build_prompt_includes_recent_history():
    prompt = build_prompt(
        CATALOG,
        text="what time does it start",
        history=[("when is the exam", "Examination timetables..."), ("ok thanks", "")],
    )
    assert "Recent conversation" in prompt
    assert "when is the exam" in prompt
    assert "what time does it start" in prompt


def test_build_prompt_drops_history_beyond_last_two_turns():
    prompt = build_prompt(
        CATALOG,
        text="now",
        history=[("a", "x"), ("b", "y"), ("c", "z")],  # 3 turns
    )
    # Only the last two should appear
    assert "User: a" not in prompt
    assert "User: b" in prompt
    assert "User: c" in prompt


# ----- catalog loader ----------------------------------------------------
def test_catalog_loads_from_canonical_file():
    catalog = load_catalog_from_file()
    names = {entry.name for entry in catalog}
    assert {"library.hours", "exam.schedule"}.issubset(names)
    # Each entry has at least one training-phrase example
    assert all(entry.examples for entry in catalog)


# ----- detect_intent: happy path -----------------------------------------
def test_detect_intent_happy_path_returns_intent_and_confidence():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({
            "response": json.dumps({"intent": "library.hours", "confidence": 0.92})
        })
        result = client.detect_intent(session="s", text="when is the library open")
    assert result.intent == "library.hours"
    assert result.confidence == pytest.approx(0.92)
    # Sanity: the call hit /api/generate on the configured host with JSON format
    args, kwargs = post.call_args
    assert args[0] == "http://x/api/generate"
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["stream"] is False


def test_detect_intent_clamps_confidence_to_unit_interval():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({
            "response": json.dumps({"intent": "library.hours", "confidence": 1.7})
        })
        result = client.detect_intent(session="s", text="hi")
    assert result.confidence == 1.0


# ----- detect_intent: failure modes -------------------------------------
def test_detect_intent_rejects_hallucinated_intent():
    """If Gemma returns an intent not in the catalog, treat it as no-intent."""
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({
            "response": json.dumps({"intent": "gpa.lookup", "confidence": 0.9})
        })
        result = client.detect_intent(session="s", text="what's my gpa")
    assert result.intent == ""
    assert result.confidence == 0.0


def test_detect_intent_treats_unknown_as_no_intent():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({
            "response": json.dumps({"intent": "unknown", "confidence": 0.4})
        })
        result = client.detect_intent(session="s", text="abracadabra")
    assert result.intent == ""


def test_detect_intent_handles_malformed_json():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({"response": "this is not json at all"})
        result = client.detect_intent(session="s", text="hi")
    assert result.intent == ""
    assert result.confidence == 0.0


def test_detect_intent_handles_ollama_unreachable():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post", side_effect=requests.ConnectionError("nope")):
        result = client.detect_intent(session="s", text="hi")
    assert result.intent == ""
    assert result.confidence == 0.0


def test_detect_intent_handles_5xx_from_ollama():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    bad = MagicMock(spec=requests.Response)
    bad.status_code = 500
    bad.raise_for_status.side_effect = requests.HTTPError(response=bad)
    with patch("app.gemma.requests.post", return_value=bad):
        result = client.detect_intent(session="s", text="hi")
    assert result.intent == ""


def test_detect_intent_handles_non_numeric_confidence():
    client = GemmaClient(catalog=CATALOG, base_url="http://x")
    with patch("app.gemma.requests.post") as post:
        post.return_value = _fake_response({
            "response": json.dumps({"intent": "library.hours", "confidence": "high"})
        })
        result = client.detect_intent(session="s", text="hi")
    # Garbage confidence → 0.0, but intent name is valid so it survives
    assert result.intent == "library.hours"
    assert result.confidence == 0.0


# ----- backend switch ----------------------------------------------------
def test_make_nlp_client_defaults_to_dialogflow(monkeypatch):
    monkeypatch.delenv("CHATBOT_NLP_BACKEND", raising=False)
    assert isinstance(make_nlp_client_from_env(), DialogflowClient)


def test_make_nlp_client_picks_gemma_when_env_set(monkeypatch):
    monkeypatch.setenv("CHATBOT_NLP_BACKEND", "gemma")
    client = make_nlp_client_from_env()
    assert isinstance(client, GemmaClient)


def test_make_nlp_client_falls_back_when_gemma_unselected(monkeypatch):
    monkeypatch.setenv("CHATBOT_NLP_BACKEND", "something-else")
    assert isinstance(make_nlp_client_from_env(), DialogflowClient)
