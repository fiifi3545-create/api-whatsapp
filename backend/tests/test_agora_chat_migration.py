"""Tests for the Agora Chat group mirror + the /webhooks/agora endpoint.

Covers:
  - GroupService mirrors create/join/delete into a chat mirror stub
  - Webhook signature gate (MD5 and HMAC-SHA256 accepted, empty secret = dev pass)
  - Webhook dispatches to bot on 1:1 to 'bot' and group msg with @bot mention
  - Unrelated group msgs are persisted but the bot stays silent
  - Bot self-messages are ignored (no loop)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest

from app import create_app
from app.agora import AgoraConfig
from app.groups import GroupService
from app.store import InMemoryStore


# ----- GroupService chat mirror -----------------------------------------
class _FakeMirror:
    def __init__(self, chat_group_id="cg-1", create_ok=True, add_ok=True, delete_ok=True):
        self.create_calls = []
        self.add_calls = []
        self.remove_calls = []
        self.delete_calls = []
        self._chat_group_id = chat_group_id
        self._create_ok = create_ok
        self._add_ok = add_ok
        self._delete_ok = delete_ok

    def create_chat_group(self, *, name, owner, members=None):
        self.create_calls.append({"name": name, "owner": owner, "members": list(members or [])})
        return self._chat_group_id if self._create_ok else None

    def add_member(self, *, chat_group_id, username):
        self.add_calls.append({"chat_group_id": chat_group_id, "username": username})
        return self._add_ok

    def remove_member(self, *, chat_group_id, username):
        self.remove_calls.append({"chat_group_id": chat_group_id, "username": username})
        return True

    def delete_chat_group(self, chat_group_id):
        self.delete_calls.append(chat_group_id)
        return self._delete_ok


def test_create_mirrors_to_chat():
    store = InMemoryStore()
    mirror = _FakeMirror(chat_group_id="cg-42")
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="CS401", creator_id="alice")
    assert group.agora_chat_group_id == "cg-42"
    assert mirror.create_calls == [
        {"name": "CS401", "owner": "alice", "members": ["alice"]}
    ]


def test_create_without_mirror_leaves_chat_id_empty():
    store = InMemoryStore()
    svc = GroupService(store, chat_mirror=None)
    group = svc.create(name="X", creator_id="u1")
    assert group.agora_chat_group_id == ""


def test_create_tolerates_mirror_failure():
    store = InMemoryStore()
    mirror = _FakeMirror(create_ok=False)
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="X", creator_id="u1")
    assert group.agora_chat_group_id == ""
    # Local group still exists.
    assert store.get_group(group.group_id) is not None


def test_join_mirrors_add_member():
    store = InMemoryStore()
    mirror = _FakeMirror(chat_group_id="cg-7")
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="Study", creator_id="alice")
    joined = svc.join(code=group.join_code, user_id="bob")
    assert joined is not None
    assert "bob" in joined.members
    assert mirror.add_calls == [{"chat_group_id": "cg-7", "username": "bob"}]


def test_join_without_chat_id_skips_mirror():
    store = InMemoryStore()
    mirror = _FakeMirror(create_ok=False)  # chat_group_id stays empty
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="X", creator_id="alice")
    svc.join(code=group.join_code, user_id="bob")
    assert mirror.add_calls == []  # mirror not called because no chat id


def test_delete_mirrors_to_chat():
    store = InMemoryStore()
    mirror = _FakeMirror(chat_group_id="cg-99")
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="X", creator_id="alice")
    ok = svc.delete(group.group_id, requester_id="alice")
    assert ok
    assert mirror.delete_calls == ["cg-99"]


def test_delete_not_creator_does_not_call_mirror():
    store = InMemoryStore()
    mirror = _FakeMirror(chat_group_id="cg-1")
    svc = GroupService(store, chat_mirror=mirror)
    group = svc.create(name="X", creator_id="alice")
    ok = svc.delete(group.group_id, requester_id="eve")
    assert ok is False
    assert mirror.delete_calls == []


# ----- /webhooks/agora --------------------------------------------------
SECRET = "wh-secret"


def _post(client, body: dict, signature: str | None):
    raw = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["Signature"] = signature
    return client.post("/webhooks/agora", data=raw, headers=headers)


def _md5_sig(body: dict) -> str:
    raw = json.dumps(body).encode("utf-8")
    return hashlib.md5(SECRET.encode() + raw).hexdigest()


def _hmac_sig(body: dict) -> str:
    raw = json.dumps(body).encode("utf-8")
    return hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


@pytest.fixture
def app_with_secret(monkeypatch):
    monkeypatch.setenv("AGORA_CHAT_WEBHOOK_SECRET", SECRET)
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app_dev_no_secret(monkeypatch):
    monkeypatch.setenv("AGORA_CHAT_WEBHOOK_SECRET", "")
    app = create_app()
    app.config["TESTING"] = True
    return app


def _txt_msg(*, from_user: str, to: str, msg: str, group: bool = False) -> dict:
    return {
        "callId": "test-call",
        "from": from_user,
        "to": to,
        "chat_type": "groupchat" if group else "chat",
        "payload": {"bodies": [{"type": "txt", "msg": msg}]},
    }


def test_webhook_rejects_missing_signature_when_secret_configured(app_with_secret):
    client = app_with_secret.test_client()
    resp = _post(client, _txt_msg(from_user="alice", to="bot", msg="hi"), signature=None)
    assert resp.status_code == 403


def test_webhook_rejects_wrong_signature(app_with_secret):
    client = app_with_secret.test_client()
    resp = _post(client, _txt_msg(from_user="alice", to="bot", msg="hi"),
                 signature="deadbeef")
    assert resp.status_code == 403


def test_webhook_accepts_md5_signature(app_with_secret):
    client = app_with_secret.test_client()
    body = _txt_msg(from_user="alice", to="bot", msg="library hours?")
    resp = _post(client, body, signature=_md5_sig(body))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["received"] == 1


def test_webhook_accepts_hmac_signature(app_with_secret):
    client = app_with_secret.test_client()
    body = _txt_msg(from_user="alice", to="bot", msg="library hours?")
    resp = _post(client, body, signature=_hmac_sig(body))
    assert resp.status_code == 200


def test_webhook_dev_mode_skips_signature(app_dev_no_secret):
    client = app_dev_no_secret.test_client()
    body = _txt_msg(from_user="alice", to="bot", msg="library hours?")
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200


def test_webhook_persists_inbound_and_bot_reply_for_1to1(app_dev_no_secret):
    client = app_dev_no_secret.test_client()
    store = app_dev_no_secret.extensions["store"]
    body = _txt_msg(from_user="233200000001", to="bot", msg="library hours?")
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["replied"] is True
    # Session keyed by sender for 1:1 chat.
    msgs = store.recent_messages("233200000001")
    assert [m.direction for m in msgs] == ["in", "out"]
    assert "library" in msgs[1].text.lower() or "examination" not in msgs[1].text.lower()


def test_webhook_group_chat_without_mention_persists_but_does_not_reply(app_dev_no_secret):
    client = app_dev_no_secret.test_client()
    store = app_dev_no_secret.extensions["store"]
    body = _txt_msg(from_user="alice", to="cg-1", msg="just chatting", group=True)
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["received"] == 1
    assert data["replied"] is False
    msgs = store.recent_messages("cg-1")
    assert [m.direction for m in msgs] == ["in"]


def test_webhook_group_chat_with_mention_triggers_bot(app_dev_no_secret):
    client = app_dev_no_secret.test_client()
    store = app_dev_no_secret.extensions["store"]
    body = _txt_msg(from_user="alice", to="cg-1",
                    msg="@bot library hours?", group=True)
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200
    assert resp.get_json()["replied"] is True
    msgs = store.recent_messages("cg-1")
    assert [m.direction for m in msgs] == ["in", "out"]
    assert msgs[1].sender_id == "bot"


def test_webhook_ignores_bot_self_messages(app_dev_no_secret):
    """Without this we'd loop: bot reply → callback → bot reply → ..."""
    client = app_dev_no_secret.test_client()
    body = _txt_msg(from_user="bot", to="alice", msg="echo")
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200
    assert resp.get_json()["received"] == 0


def test_webhook_handles_non_text_bodies_gracefully(app_dev_no_secret):
    client = app_dev_no_secret.test_client()
    body = {
        "from": "alice",
        "to": "bot",
        "chat_type": "chat",
        "payload": {"bodies": [{"type": "img", "url": "http://x"}]},
    }
    resp = _post(client, body, signature=None)
    assert resp.status_code == 200
    assert resp.get_json()["received"] == 0
