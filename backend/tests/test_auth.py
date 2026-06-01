import time

import jwt
import pytest

from app import create_app
from app.auth import issue_jwt


JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config["JWT_TTL_DAYS"] = 1
    app.config["OTP_ECHO_IN_RESPONSE"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ----- OTP flow ------------------------------------------------------
def test_request_otp_returns_code_in_dev(client):
    resp = client.post("/api/auth/request-otp", json={"phone_number": "233200000001"})
    assert resp.status_code == 202
    body = resp.get_json()
    # `sent` reflects WhatsApp template delivery. In tests there are no
    # WhatsApp credentials, so the send is a no-op and `sent` is False.
    assert body["sent"] is False
    assert len(body["otp"]) == 6
    assert body["otp"].isdigit()


def test_request_otp_missing_phone_returns_422(client):
    resp = client.post("/api/auth/request-otp", json={})
    assert resp.status_code == 422


def test_verify_otp_happy_path_returns_jwt(client):
    issued = client.post(
        "/api/auth/request-otp", json={"phone_number": "233200000001"}
    ).get_json()
    resp = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "233200000001", "code": issued["otp"]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user_id"] == "233200000001"
    decoded = jwt.decode(body["token"], JWT_SECRET, algorithms=["HS256"])
    assert decoded["sub"] == "233200000001"


def test_verify_otp_wrong_code_returns_401(client):
    client.post("/api/auth/request-otp", json={"phone_number": "233200000001"})
    resp = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "233200000001", "code": "000000"},
    )
    assert resp.status_code == 401


def test_verify_otp_unknown_phone_returns_401(client):
    resp = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "never-requested", "code": "123456"},
    )
    assert resp.status_code == 401


def test_otp_is_single_use(client):
    issued = client.post(
        "/api/auth/request-otp", json={"phone_number": "233200000001"}
    ).get_json()
    first = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "233200000001", "code": issued["otp"]},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "233200000001", "code": issued["otp"]},
    )
    assert second.status_code == 401


# ----- @require_auth -------------------------------------------------
def test_protected_route_without_token_returns_401(client):
    resp = client.get("/api/users/u1")
    assert resp.status_code == 401


def test_protected_route_with_malformed_header_returns_401(client):
    resp = client.get("/api/users/u1", headers={"Authorization": "Token foo"})
    assert resp.status_code == 401


def test_protected_route_with_invalid_signature_returns_401(client):
    bad = jwt.encode({"sub": "u1", "exp": int(time.time()) + 60}, "wrong-secret", algorithm="HS256")
    resp = client.get("/api/users/u1", headers={"Authorization": f"Bearer {bad}"})
    assert resp.status_code == 401


def test_protected_route_with_expired_token_returns_401(client):
    expired = jwt.encode(
        {"sub": "u1", "exp": int(time.time()) - 10},
        JWT_SECRET,
        algorithm="HS256",
    )
    resp = client.get("/api/users/u1", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


def test_subject_mismatch_returns_403(client):
    token = issue_jwt(user_id="u1", secret=JWT_SECRET, ttl_days=1)
    resp = client.get("/api/users/u2", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
