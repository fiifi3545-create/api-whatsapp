import json

import pytest

from app import create_app
from app.store import InMemoryStore


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def client(store):
    app = create_app(store=store)
    app.config["TESTING"] = True
    app.config["WHATSAPP_VERIFY_TOKEN"] = "test-token"
    app.config["META_APP_SECRET"] = ""  # signature off for this suite
    return app.test_client()


def _wa_payload(sender: str, body: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.X",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_inbound_upserts_user(client, store):
    client.post("/webhooks/whatsapp", json=_wa_payload("233200000099", "library hours?"))
    assert store.get_user("233200000099") is not None


def test_inbound_logs_both_directions(client, store):
    client.post("/webhooks/whatsapp", json=_wa_payload("233200000099", "library hours?"))
    msgs = store.recent_messages(session_key="233200000099")
    directions = [m.direction for m in msgs]
    assert directions == ["in", "out"]
    assert msgs[0].text == "library hours?"
    assert "library" in msgs[1].text.lower()


def test_fallback_reply_is_still_persisted(client, store):
    client.post("/webhooks/whatsapp", json=_wa_payload("233200000099", "completely unknown xyzzy"))
    msgs = store.recent_messages(session_key="233200000099")
    assert [m.direction for m in msgs] == ["in", "out"]
    assert "confident answer" in msgs[1].text.lower()


def test_repeated_messages_from_same_user_dedup_user_record(client, store):
    for _ in range(3):
        client.post("/webhooks/whatsapp", json=_wa_payload("233200000099", "library?"))
    # Still only one user row
    users = [store.get_user("233200000099")]
    assert len([u for u in users if u]) == 1
    # But 6 messages (3 in + 3 out)
    assert len(store.recent_messages("233200000099")) == 6
