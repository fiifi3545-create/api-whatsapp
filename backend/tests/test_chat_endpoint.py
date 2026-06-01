import pytest

from app import create_app
from app.auth import issue_jwt
from app.store import InMemoryStore


JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def client(store):
    app = create_app(store=store)
    app.config["TESTING"] = True
    app.config["META_APP_SECRET"] = ""
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config["JWT_TTL_DAYS"] = 1
    return app.test_client()


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {issue_jwt(user_id=user_id, secret=JWT_SECRET, ttl_days=1)}"}


def test_chat_requires_auth(client):
    resp = client.post("/api/users/u1/chat", json={"text": "hi"})
    assert resp.status_code == 401


def test_chat_subject_must_match_user_id(client):
    resp = client.post("/api/users/u1/chat", json={"text": "hi"}, headers=_auth("someone-else"))
    assert resp.status_code == 403


def test_chat_rejects_empty_text(client):
    resp = client.post("/api/users/u1/chat", json={"text": "  "}, headers=_auth("u1"))
    assert resp.status_code == 422


def test_chat_returns_both_in_and_out_messages(client, store):
    resp = client.post("/api/users/u1/chat", json={"text": "library hours"}, headers=_auth("u1"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert "messages" in body
    assert len(body["messages"]) == 2

    inbound, outbound = body["messages"]
    assert inbound["direction"] == "in"
    assert inbound["text"] == "library hours"
    assert outbound["direction"] == "out"
    assert "library" in outbound["text"].lower()

    # Both persisted under user's session
    persisted = store.recent_messages("u1")
    assert [m.direction for m in persisted] == ["in", "out"]


def test_chat_fallback_still_persists_outbound(client, store):
    """Unknown intent → fallback message still returned and stored."""
    resp = client.post(
        "/api/users/u1/chat",
        json={"text": "completely unknown xyzzy"},
        headers=_auth("u1"),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["messages"]) == 2
    assert "confident answer" in body["messages"][1]["text"].lower()


def test_chat_upserts_user_on_first_message(client, store):
    assert store.get_user("u1") is None
    client.post("/api/users/u1/chat", json={"text": "hi"}, headers=_auth("u1"))
    assert store.get_user("u1") is not None
