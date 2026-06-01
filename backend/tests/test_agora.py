"""Tests for Agora token minting + the /api/agora/* endpoints."""

from __future__ import annotations

import time

import jwt
import pytest

from app import create_app
from app.agora import (
    AgoraClient,
    AgoraConfig,
    AgoraNotConfigured,
    RTC_ROLE_PUBLISHER,
    _sanitize_chat_username,
)
from app.auth import issue_jwt


JWT_SECRET = "test-jwt-secret"
APP_ID = "0123456789abcdef0123456789abcdef"
APP_CERT = "fedcba9876543210fedcba9876543210"
CHAT_APP_KEY = "411357079#200044046"


@pytest.fixture
def configured_agora_app(monkeypatch):
    monkeypatch.setenv("AGORA_APP_ID", APP_ID)
    monkeypatch.setenv("AGORA_APP_CERTIFICATE", APP_CERT)
    monkeypatch.setenv("AGORA_CHAT_APP_KEY", CHAT_APP_KEY)
    monkeypatch.setenv("AGORA_CHAT_REST_HOST", "msync-api-41.chat.agora.io")
    app = create_app()
    app.config["TESTING"] = True
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config["JWT_TTL_DAYS"] = 1
    return app


@pytest.fixture
def unconfigured_agora_app(monkeypatch):
    # setenv("") so load_dotenv() in create_app (override=False by default)
    # leaves these empty rather than re-reading the real .env.
    monkeypatch.setenv("AGORA_APP_ID", "")
    monkeypatch.setenv("AGORA_APP_CERTIFICATE", "")
    app = create_app()
    app.config["TESTING"] = True
    app.config["JWT_SECRET"] = JWT_SECRET
    return app


def _auth(user_id: str = "233200000001") -> dict:
    token = issue_jwt(user_id=user_id, secret=JWT_SECRET, ttl_days=1)
    return {"Authorization": f"Bearer {token}"}


# ----- Pure helper tests -----------------------------------------------
def test_sanitize_chat_username_passes_phone_number():
    assert _sanitize_chat_username("233200000001") == "233200000001"


def test_sanitize_chat_username_replaces_disallowed_chars():
    assert _sanitize_chat_username("user+name@x") == "user_name_x"


def test_sanitize_chat_username_truncates_to_64():
    out = _sanitize_chat_username("a" * 200)
    assert len(out) == 64


def test_sanitize_chat_username_empty_becomes_default():
    assert _sanitize_chat_username("") == "user"


# ----- AgoraClient unit tests ------------------------------------------
def test_rtc_token_returns_expected_shape():
    client = AgoraClient(AgoraConfig(
        app_id=APP_ID, app_certificate=APP_CERT,
        chat_app_key="", chat_rest_host="", chat_app_token="",
    ))
    result = client.rtc_token(channel="g-1", uid=42, role=RTC_ROLE_PUBLISHER, ttl=600)
    assert result["app_id"] == APP_ID
    assert result["channel"] == "g-1"
    assert result["uid"] == 42
    assert result["role"] == RTC_ROLE_PUBLISHER
    assert isinstance(result["token"], str) and result["token"].startswith("006")
    assert result["expires_at"] > int(time.time())


def test_rtc_token_requires_channel():
    client = AgoraClient(AgoraConfig(
        app_id=APP_ID, app_certificate=APP_CERT,
        chat_app_key="", chat_rest_host="", chat_app_token="",
    ))
    with pytest.raises(ValueError):
        client.rtc_token(channel="", uid=0)


def test_rtm_token_returns_expected_shape():
    client = AgoraClient(AgoraConfig(
        app_id=APP_ID, app_certificate=APP_CERT,
        chat_app_key="", chat_rest_host="", chat_app_token="",
    ))
    result = client.rtm_token(user_id="233200000001", ttl=600)
    assert result["user_id"] == "233200000001"
    assert isinstance(result["token"], str)
    assert result["expires_at"] > int(time.time())


def test_chat_user_token_is_verifiable_jwt():
    client = AgoraClient(AgoraConfig(
        app_id=APP_ID, app_certificate=APP_CERT,
        chat_app_key=CHAT_APP_KEY, chat_rest_host="x", chat_app_token="",
    ))
    result = client.chat_user_token(user_id="233200000001", ttl=600)
    assert result["app_key"] == CHAT_APP_KEY
    assert result["rest_host"] == "x"
    decoded = jwt.decode(result["token"], APP_CERT, algorithms=["HS256"])
    assert decoded["iss"] == APP_ID
    assert decoded["chatUserName"] == "233200000001"
    assert decoded["exp"] == result["expires_at"]


def test_unconfigured_client_raises():
    client = AgoraClient(AgoraConfig(
        app_id="", app_certificate="", chat_app_key="", chat_rest_host="", chat_app_token="",
    ))
    with pytest.raises(AgoraNotConfigured):
        client.rtc_token(channel="x")
    with pytest.raises(AgoraNotConfigured):
        client.rtm_token(user_id="u")
    with pytest.raises(AgoraNotConfigured):
        client.chat_user_token(user_id="u")


# ----- Endpoint tests --------------------------------------------------
def test_rtc_token_endpoint_returns_token(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post(
        "/api/agora/rtc-token",
        headers=_auth(),
        json={"channel": "group-abc", "uid": 0, "role": "publisher"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["app_id"] == APP_ID
    assert body["channel"] == "group-abc"
    assert body["token"]


def test_rtc_token_endpoint_clamps_ttl(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post(
        "/api/agora/rtc-token",
        headers=_auth(),
        json={"channel": "x", "ttl_seconds": 999999},
    )
    body = resp.get_json()
    # Clamped to 24h max.
    assert body["expires_at"] - int(time.time()) <= 24 * 3600 + 5


def test_rtc_token_endpoint_requires_channel(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post("/api/agora/rtc-token", headers=_auth(), json={})
    assert resp.status_code == 400


def test_rtc_token_endpoint_requires_auth(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post("/api/agora/rtc-token", json={"channel": "x"})
    assert resp.status_code == 401


def test_rtm_token_endpoint_binds_to_jwt_subject(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post(
        "/api/agora/rtm-token",
        headers=_auth("233200000099"),
        json={},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user_id"] == "233200000099"
    assert body["token"]


def test_chat_token_endpoint_returns_jwt(configured_agora_app):
    client = configured_agora_app.test_client()
    resp = client.post(
        "/api/agora/chat-token",
        headers=_auth("233200000001"),
        json={},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["app_key"] == CHAT_APP_KEY
    assert body["rest_host"] == "msync-api-41.chat.agora.io"
    decoded = jwt.decode(body["token"], APP_CERT, algorithms=["HS256"])
    assert decoded["chatUserName"] == "233200000001"


def test_endpoint_returns_503_when_agora_unconfigured(unconfigured_agora_app):
    client = unconfigured_agora_app.test_client()
    for path in ("/api/agora/rtc-token", "/api/agora/rtm-token", "/api/agora/chat-token"):
        resp = client.post(
            path,
            headers=_auth(),
            json={"channel": "x"} if "rtc" in path else {},
        )
        assert resp.status_code == 503, f"{path} should 503 when unconfigured"
