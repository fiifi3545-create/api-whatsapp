import hashlib
import hmac
import json

import pytest

from app import create_app
from app.security import verify_meta_signature


SECRET = "test-app-secret"


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def signed_client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WHATSAPP_VERIFY_TOKEN"] = "test-token"
    app.config["META_APP_SECRET"] = SECRET
    return app.test_client()


def test_verify_returns_true_when_secret_empty():
    assert verify_meta_signature("", b"{}", None) is True


def test_verify_rejects_missing_header_when_secret_set():
    assert verify_meta_signature(SECRET, b"{}", None) is False


def test_verify_rejects_malformed_header():
    assert verify_meta_signature(SECRET, b"{}", "deadbeef") is False


def test_verify_accepts_correct_signature():
    body = b'{"hello":"world"}'
    sig = _sign(body)
    assert verify_meta_signature(SECRET, body, sig) is True


def test_verify_rejects_wrong_signature():
    body = b'{"hello":"world"}'
    assert verify_meta_signature(SECRET, body, "sha256=" + "0" * 64) is False


def test_webhook_rejects_unsigned_post_when_secret_set(signed_client):
    resp = signed_client.post(
        "/webhooks/whatsapp",
        json={"entry": []},
    )
    assert resp.status_code == 403


def test_webhook_accepts_correctly_signed_post(signed_client):
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
                                    "text": {"body": "library hours?"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    resp = signed_client.post(
        "/webhooks/whatsapp",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"received": 1}


def test_webhook_rejects_tampered_body(signed_client):
    payload = {"entry": []}
    body = json.dumps(payload).encode()
    good_sig = _sign(body)

    resp = signed_client.post(
        "/webhooks/whatsapp",
        data=b'{"entry":[{"tampered":true}]}',
        content_type="application/json",
        headers={"X-Hub-Signature-256": good_sig},
    )
    assert resp.status_code == 403
