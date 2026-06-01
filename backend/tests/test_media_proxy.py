from unittest.mock import MagicMock, patch

import pytest
import requests

from app import create_app
from app.auth import issue_jwt
from app.store import InMemoryStore


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
    app.config["WHATSAPP_PHONE_NUMBER_ID"] = "phone-1"
    app.config["WHATSAPP_ACCESS_TOKEN"] = "fake-token"
    app.config["WHATSAPP_API_BASE"] = "https://graph.test/v20.0"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _auth() -> dict:
    return {"Authorization": f"Bearer {issue_jwt(user_id='u1', secret=JWT_SECRET, ttl_days=1)}"}


def _resp(status: int = 200, json_body: dict | None = None, content: bytes = b""):
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.content = content
    r.json.return_value = json_body or {}

    def raise_for_status():
        if status >= 400:
            err = requests.HTTPError(response=MagicMock(status_code=status))
            err.response.status_code = status
            raise err

    r.raise_for_status.side_effect = raise_for_status
    return r


# ----- auth ----------------------------------------------------------------
def test_media_requires_auth(client):
    resp = client.get("/api/media/abc123")
    assert resp.status_code == 401


# ----- happy path ----------------------------------------------------------
def test_media_proxy_returns_bytes_with_mime(client):
    meta = _resp(json_body={"url": "https://lookaside.test/x", "mime_type": "image/jpeg"})
    binary = _resp(content=b"\xff\xd8\xff\xe0JPEGBYTES")

    with patch("app.whatsapp.requests.get", side_effect=[meta, binary]) as get:
        resp = client.get("/api/media/abc123", headers=_auth())

    assert resp.status_code == 200
    assert resp.content_type.startswith("image/jpeg")
    assert resp.data == b"\xff\xd8\xff\xe0JPEGBYTES"
    assert "private" in resp.headers["Cache-Control"]

    # First call hits the media-metadata endpoint with the bearer header
    args, kwargs = get.call_args_list[0]
    assert args[0] == "https://graph.test/v20.0/abc123"
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token"
    # Second call hits the signed URL with the same bearer
    args, kwargs = get.call_args_list[1]
    assert args[0] == "https://lookaside.test/x"
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token"


# ----- failure modes -------------------------------------------------------
def test_media_returns_503_when_access_token_missing(app, client):
    app.config["WHATSAPP_ACCESS_TOKEN"] = ""
    resp = client.get("/api/media/abc123", headers=_auth())
    assert resp.status_code == 503
    assert "not configured" in resp.get_json()["error"]


def test_media_returns_404_when_graph_404s(client):
    not_found_resp = MagicMock(spec=requests.Response)
    not_found_resp.status_code = 404
    err = requests.HTTPError(response=not_found_resp)

    fake = _resp()
    fake.raise_for_status.side_effect = err

    with patch("app.whatsapp.requests.get", return_value=fake):
        resp = client.get("/api/media/missing", headers=_auth())

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "media not found"


def test_media_returns_502_on_graph_500(client):
    server_resp = MagicMock(spec=requests.Response)
    server_resp.status_code = 500
    err = requests.HTTPError(response=server_resp)

    fake = _resp()
    fake.raise_for_status.side_effect = err

    with patch("app.whatsapp.requests.get", return_value=fake):
        resp = client.get("/api/media/abc123", headers=_auth())

    assert resp.status_code == 502


def test_media_returns_502_on_network_error(client):
    with patch("app.whatsapp.requests.get", side_effect=requests.ConnectionError("boom")):
        resp = client.get("/api/media/abc123", headers=_auth())
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "upstream unreachable"


def test_media_returns_503_when_signed_url_missing(client):
    """If Graph returns metadata without a `url` field, treat it as unusable."""
    meta = _resp(json_body={"mime_type": "image/jpeg"})  # no url
    with patch("app.whatsapp.requests.get", return_value=meta):
        resp = client.get("/api/media/abc123", headers=_auth())
    assert resp.status_code == 503
