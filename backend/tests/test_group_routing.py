from unittest.mock import patch

import pytest

from app import create_app
from app.store import Group, InMemoryStore
from app.whatsapp import is_bot_mentioned, parse_incoming, strip_mention


# ---------- unit-level helpers ----------------------------------------------
def test_parse_incoming_extracts_group_id():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "233200000001",
                                    "id": "wamid.GROUP",
                                    "type": "text",
                                    "context": {"group_id": "120363000@g.us"},
                                    "text": {"body": "@bot when is the exam"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    parsed = parse_incoming(payload)
    assert len(parsed) == 1
    assert parsed[0]["group_id"] == "120363000@g.us"
    assert parsed[0]["text"] == "@bot when is the exam"


def test_parse_incoming_group_id_is_none_for_1to1():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "233200000001",
                                    "id": "wamid.X",
                                    "type": "text",
                                    "text": {"body": "hi"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    assert parse_incoming(payload)[0]["group_id"] is None


def test_is_bot_mentioned_case_insensitive():
    assert is_bot_mentioned("Hey @Bot what's up", "@bot")
    assert is_bot_mentioned("@bot help", "@bot")
    assert not is_bot_mentioned("just chatting", "@bot")
    assert not is_bot_mentioned("", "@bot")


def test_strip_mention_collapses_whitespace():
    assert strip_mention("@bot when is the exam", "@bot") == "when is the exam"
    assert strip_mention("hey @bot   library hours?", "@bot") == "hey library hours?"
    assert strip_mention("@BOT @bot duplicate", "@bot") == "duplicate"


# ---------- webhook-level routing ------------------------------------------
@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def app(store):
    app = create_app(store=store)
    app.config["TESTING"] = True
    app.config["WHATSAPP_VERIFY_TOKEN"] = "test-token"
    app.config["META_APP_SECRET"] = ""  # signature off
    app.config["BOT_MENTION_NAME"] = "@bot"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _group_payload(sender: str, group_id: str, body: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.G",
                                    "type": "text",
                                    "context": {"group_id": group_id},
                                    "text": {"body": body},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_group_message_without_mention_is_persisted_but_bot_stays_silent(client, store):
    """Bot stays out of unmentioned group chatter, but the message must still
    be persisted and broadcast — in-app members reading via the Flutter app
    see all group messages, not just bot-mention ones."""
    with patch("app.webhooks.WhatsAppClient.send_text") as send:
        resp = client.post(
            "/webhooks/whatsapp",
            json=_group_payload("233200000001", "120363000@g.us", "just chatting"),
        )
    assert resp.status_code == 200
    assert resp.get_json() == {"received": 1}

    msgs = store.recent_messages("120363000@g.us")
    assert [m.direction for m in msgs] == ["in"]  # only the inbound; no bot reply
    assert msgs[0].text == "just chatting"
    assert msgs[0].sender_id == "233200000001"
    assert store.get_user("233200000001") is not None
    send.assert_not_called()  # bot did not reply


def test_group_message_with_mention_is_handled(client, store):
    with patch("app.webhooks.WhatsAppClient.send_text") as send:
        send.return_value = None
        resp = client.post(
            "/webhooks/whatsapp",
            json=_group_payload("233200000001", "120363000@g.us", "@bot library hours?"),
        )
    assert resp.status_code == 200
    assert resp.get_json() == {"received": 1}

    msgs = store.recent_messages("120363000@g.us")
    assert [m.direction for m in msgs] == ["in", "out"]
    # Persisted text keeps the raw mention (audit-friendly), bot reads stripped.
    assert msgs[0].text == "@bot library hours?"
    # Reply is broadcast back to the group, not the sender.
    send.assert_called_once()
    kwargs = send.call_args.kwargs or dict(zip(("to", "body"), send.call_args.args))
    assert kwargs["to"] == "120363000@g.us"


def test_group_reply_pushes_to_every_member(client, store, app):
    # Pre-seed a group with three members
    store.create_group(
        Group(
            group_id="120363000@g.us",
            name="Stats Study",
            creator_id="233200000001",
            join_code="ABC123",
            members={"233200000001", "233200000002", "233200000003"},
        )
    )

    pushed_to: list[str] = []

    def fake_push(user_id, title, body, data=None):
        pushed_to.append(user_id)
        return 0

    app.extensions["pusher"].push = fake_push

    with patch("app.webhooks.WhatsAppClient.send_text", return_value=None):
        client.post(
            "/webhooks/whatsapp",
            json=_group_payload("233200000001", "120363000@g.us", "@bot library hours?"),
        )

    assert sorted(pushed_to) == sorted(
        ["233200000001", "233200000002", "233200000003"]
    )


def test_one_to_one_unchanged_by_group_routing(client, store):
    """Sanity: a 1:1 message (no group_id) still gets handled and replied to."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "233200000099",
                                    "id": "wamid.X",
                                    "type": "text",
                                    "text": {"body": "library hours?"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    with patch("app.webhooks.WhatsAppClient.send_text", return_value=None):
        resp = client.post("/webhooks/whatsapp", json=payload)
    assert resp.get_json() == {"received": 1}
    msgs = store.recent_messages("233200000099")
    assert [m.direction for m in msgs] == ["in", "out"]
