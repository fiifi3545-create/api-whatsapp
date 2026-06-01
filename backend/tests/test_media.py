import pytest

from app import create_app
from app.store import InMemoryStore
from app.whatsapp import parse_incoming


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def client(store):
    app = create_app(store=store)
    app.config["TESTING"] = True
    app.config["META_APP_SECRET"] = ""
    return app.test_client()


def test_parse_image_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "u1",
                                    "id": "wamid.x",
                                    "type": "image",
                                    "image": {"id": "media-123", "caption": "my id card"},
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
    assert parsed[0]["media_id"] == "media-123"
    assert parsed[0]["media_type"] == "image"
    assert parsed[0]["caption"] == "my id card"
    assert parsed[0]["text"] == "my id card"


def test_parse_image_without_caption_falls_back_to_placeholder():
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [
                {"from": "u1", "id": "x", "type": "image", "image": {"id": "m"}}
            ]}}]}
        ]
    }
    parsed = parse_incoming(payload)
    assert parsed[0]["text"] == "[image]"
    assert parsed[0]["caption"] is None


def test_parse_document_uses_filename_when_no_caption():
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [
                {
                    "from": "u1", "id": "x", "type": "document",
                    "document": {"id": "doc-1", "filename": "transcript.pdf"},
                }
            ]}}]}
        ]
    }
    parsed = parse_incoming(payload)
    assert parsed[0]["media_type"] == "document"
    assert parsed[0]["caption"] == "transcript.pdf"


def test_parse_unsupported_type_is_skipped():
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [
                {"from": "u1", "id": "x", "type": "audio", "audio": {"id": "a"}}
            ]}}]}
        ]
    }
    assert parse_incoming(payload) == []


def test_image_webhook_persists_media_fields(client, store):
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [
                {
                    "from": "233200000099",
                    "id": "wamid.X",
                    "type": "image",
                    "image": {"id": "media-99", "caption": "this is my receipt"},
                }
            ]}}]}
        ]
    }
    resp = client.post("/webhooks/whatsapp", json=payload)
    assert resp.status_code == 200
    msgs = store.recent_messages("233200000099")
    inbound = msgs[0]
    assert inbound.media_type == "image"
    assert inbound.media_url == "media-99"
    assert inbound.caption == "this is my receipt"
