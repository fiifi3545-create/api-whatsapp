from unittest.mock import MagicMock, patch

import requests

from app.chatbot import ChatbotEngine, make_nlp_client_from_env
from app.gemini import GeminiClient


def _fake_response(json_body: dict, status: int = 200) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.json.return_value = json_body
    r.raise_for_status.return_value = None
    return r


def _candidate(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


# ----- generate_reply: happy path ---------------------------------------
def test_generate_reply_returns_candidate_text():
    client = GeminiClient(api_key="k", model="gemini-test-model")
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response(_candidate("The library opens at 8am."))
        answer = client.generate_reply(session="s", text="When does the library open?")
    assert answer == "The library opens at 8am."
    args, kwargs = post.call_args
    assert args[0].endswith("/models/gemini-test-model:generateContent")
    assert kwargs["params"] == {"key": "k"}
    # First (and only) content item is the user's current message.
    assert kwargs["json"]["contents"][-1]["parts"][0]["text"] == "When does the library open?"
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"]


def test_generate_reply_concatenates_multipart_response():
    client = GeminiClient(api_key="k")
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "Hello "}, {"text": "world."}]}}
        ]
    }
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response(payload)
        answer = client.generate_reply(session="s", text="hi")
    assert answer == "Hello world."


def test_generate_reply_forwards_recent_history_as_alternating_roles():
    client = GeminiClient(api_key="k")
    history = [
        ("When is the exam?", "Examination timetables are posted on the portal."),
        ("Which portal?", "The university student portal at portal.uni.edu."),
    ]
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response(_candidate("Yes."))
        client.generate_reply(session="s", text="Got it, thanks", history=history)
    contents = post.call_args.kwargs["json"]["contents"]
    roles = [c["role"] for c in contents]
    assert roles == ["user", "model", "user", "model", "user"]
    assert contents[0]["parts"][0]["text"] == "When is the exam?"
    assert contents[-1]["parts"][0]["text"] == "Got it, thanks"


def test_generate_reply_caps_forwarded_history_to_last_four_turns():
    client = GeminiClient(api_key="k")
    history = [(f"q{i}", f"a{i}") for i in range(10)]  # 10 turns
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response(_candidate("ok"))
        client.generate_reply(session="s", text="now", history=history)
    contents = post.call_args.kwargs["json"]["contents"]
    # 4 turns × 2 messages + 1 current = 9; older turns must be dropped.
    assert len(contents) == 9
    assert contents[0]["parts"][0]["text"] == "q6"


# ----- generate_reply: failure modes ------------------------------------
def test_generate_reply_without_api_key_returns_empty(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient(api_key="")
    with patch("app.gemini.requests.post") as post:
        answer = client.generate_reply(session="s", text="hi")
    assert answer == ""
    post.assert_not_called()  # never hit the network without a key


def test_generate_reply_handles_network_error():
    client = GeminiClient(api_key="k")
    with patch("app.gemini.requests.post", side_effect=requests.ConnectionError("nope")):
        answer = client.generate_reply(session="s", text="hi")
    assert answer == ""


def test_generate_reply_handles_http_error():
    client = GeminiClient(api_key="k")
    bad = MagicMock(spec=requests.Response)
    bad.status_code = 500
    bad.raise_for_status.side_effect = requests.HTTPError(response=bad)
    with patch("app.gemini.requests.post", return_value=bad):
        answer = client.generate_reply(session="s", text="hi")
    assert answer == ""


def test_generate_reply_handles_empty_candidates():
    client = GeminiClient(api_key="k")
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response({"candidates": []})
        answer = client.generate_reply(session="s", text="hi")
    assert answer == ""


def test_generate_reply_handles_missing_parts():
    client = GeminiClient(api_key="k")
    with patch("app.gemini.requests.post") as post:
        post.return_value = _fake_response({"candidates": [{"content": {}}]})
        answer = client.generate_reply(session="s", text="hi")
    assert answer == ""


# ----- ChatbotEngine integration ----------------------------------------
class _StubDirectReply:
    """Drop-in for GeminiClient that returns a canned answer per call."""
    def __init__(self, answer="The library opens at 8am.", calls=None):
        self.answer = answer
        self.calls = calls if calls is not None else []

    def generate_reply(self, session, text, history=None):
        self.calls.append({"session": session, "text": text, "history": list(history or [])})
        return self.answer


def test_engine_uses_generate_reply_when_backend_supports_it():
    engine = ChatbotEngine(nlp=_StubDirectReply(answer="Hi there!"))
    reply = engine.handle(user_id="u1", text="hello")
    assert reply == "Hi there!"


def test_engine_falls_back_when_direct_reply_returns_empty():
    engine = ChatbotEngine(nlp=_StubDirectReply(answer=""))
    reply = engine.handle(user_id="u1", text="something obscure")
    assert "confident answer" in reply.lower()


def test_engine_passes_prior_history_into_generate_reply():
    stub = _StubDirectReply(answer="ok")
    engine = ChatbotEngine(nlp=stub)
    engine.handle(user_id="u1", text="first")
    engine.handle(user_id="u1", text="second")
    # Second call should see the first turn as history.
    assert stub.calls[1]["history"] == [("first", "ok")]


# ----- backend factory --------------------------------------------------
def test_make_nlp_client_picks_gemini_when_env_set(monkeypatch):
    monkeypatch.setenv("CHATBOT_NLP_BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client = make_nlp_client_from_env()
    assert isinstance(client, GeminiClient)
    assert client.api_key == "k"
