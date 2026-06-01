import pytest

from app import create_app
from app.auth import issue_jwt
from app.push import FcmPusher
from app.store import Device, InMemoryStore


JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def app(store):
    app = create_app(store=store)
    app.config["TESTING"] = True
    app.config["META_APP_SECRET"] = ""
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config["JWT_TTL_DAYS"] = 1
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(user_id: str) -> dict:
    return {
        "Authorization": f"Bearer {issue_jwt(user_id=user_id, secret=JWT_SECRET, ttl_days=1)}"
    }


def test_register_device_returns_201(client):
    resp = client.post(
        "/api/users/u1/devices",
        json={"fcm_token": "tok-abc", "platform": "android"},
        headers=_auth("u1"),
    )
    assert resp.status_code == 201
    assert resp.get_json()["fcm_token"] == "tok-abc"


def test_register_device_rejects_unknown_platform(client):
    resp = client.post(
        "/api/users/u1/devices",
        json={"fcm_token": "tok", "platform": "blackberry"},
        headers=_auth("u1"),
    )
    assert resp.status_code == 422


def test_register_device_requires_token(client):
    resp = client.post(
        "/api/users/u1/devices",
        json={"platform": "android"},
        headers=_auth("u1"),
    )
    assert resp.status_code == 422


def test_register_device_enforces_subject(client):
    resp = client.post(
        "/api/users/u1/devices",
        json={"fcm_token": "tok", "platform": "android"},
        headers=_auth("u2"),
    )
    assert resp.status_code == 403


def test_unregister_device_returns_204(client, store):
    store.register_device(Device(user_id="u1", fcm_token="tok-x", platform="ios"))
    resp = client.delete("/api/users/u1/devices/tok-x", headers=_auth("u1"))
    assert resp.status_code == 204


def test_unregister_unknown_device_returns_404(client):
    resp = client.delete("/api/users/u1/devices/nope", headers=_auth("u1"))
    assert resp.status_code == 404


def test_register_is_idempotent(client, store):
    for _ in range(3):
        client.post(
            "/api/users/u1/devices",
            json={"fcm_token": "tok", "platform": "android"},
            headers=_auth("u1"),
        )
    assert len(store.list_devices("u1")) == 1


# ----- FcmPusher stub behavior --------------------------------------
def test_pusher_with_no_devices_returns_zero(store):
    pusher = FcmPusher(store=store)
    assert pusher.push(user_id="u1", title="t", body="b") == 0


def test_pusher_stub_returns_zero_even_with_devices(store):
    store.register_device(Device(user_id="u1", fcm_token="tok", platform="android"))
    pusher = FcmPusher(store=store)  # no FCM_PROJECT_ID set → stub
    assert pusher.push(user_id="u1", title="t", body="b") == 0


def test_webhook_inbound_does_not_raise_when_pusher_is_stub(client, store):
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
    resp = client.post("/webhooks/whatsapp", json=payload)
    assert resp.status_code == 200
