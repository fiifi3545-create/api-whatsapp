"""Tests for POST /api/calls/notify — the call-start ringing endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import create_app
from app.auth import issue_jwt
from app.store import Group, InMemoryStore, User


JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def pusher():
    """A spy-able FCM pusher. We inject it via create_app so the endpoint
    sees our recorder instead of the env-built no-op stub."""
    return MagicMock(spec=["push"])


@pytest.fixture
def app(store, pusher):
    app = create_app(store=store, pusher=pusher)
    app.config["TESTING"] = True
    app.config["JWT_SECRET"] = JWT_SECRET
    app.config["JWT_TTL_DAYS"] = 1
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {issue_jwt(user_id=user_id, secret=JWT_SECRET, ttl_days=1)}"}


def _setup_group(store, *, group_id="g1", name="CS401", creator="alice",
                 extra_members=("bob", "carol")):
    members = {creator, *extra_members}
    store.create_group(Group(
        group_id=group_id, name=name, creator_id=creator,
        join_code="XX", members=members,
    ))
    for uid in members:
        store.upsert_user(User(user_id=uid, name=uid.title()))


# ----- happy path ------------------------------------------------------
def test_notify_fans_out_to_other_members(client, store, pusher):
    _setup_group(store)
    resp = client.post(
        "/api/calls/notify",
        headers=_auth("alice"),
        json={"group_id": "g1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["notified"] == 2  # bob + carol, alice excluded

    assert pusher.push.call_count == 2
    called_recipients = {call.kwargs["user_id"] for call in pusher.push.call_args_list}
    assert called_recipients == {"bob", "carol"}


def test_notify_payload_carries_call_invitation_data(client, store, pusher):
    _setup_group(store)
    client.post(
        "/api/calls/notify",
        headers=_auth("alice"),
        json={"group_id": "g1"},
    )
    # Inspect the first push to bob.
    bob_call = next(
        c for c in pusher.push.call_args_list if c.kwargs["user_id"] == "bob"
    )
    data = bob_call.kwargs["data"]
    assert data["type"] == "call_invitation"
    assert data["group_id"] == "g1"
    assert data["group_name"] == "CS401"
    assert data["initiator_id"] == "alice"
    assert data["initiator_name"] == "Alice"  # display name from User.name


def test_notify_uses_user_id_when_display_name_missing(client, store, pusher):
    store.create_group(Group(
        group_id="g1", name="X", creator_id="233200000001",
        join_code="X", members={"233200000001", "233200000099"},
    ))
    # No upsert_user → no display name → fallback to user_id
    client.post(
        "/api/calls/notify",
        headers=_auth("233200000001"),
        json={"group_id": "g1"},
    )
    data = pusher.push.call_args.kwargs["data"]
    assert data["initiator_name"] == "233200000001"


# ----- error paths -----------------------------------------------------
def test_notify_requires_auth(client, store):
    _setup_group(store)
    resp = client.post("/api/calls/notify", json={"group_id": "g1"})
    assert resp.status_code == 401


def test_notify_requires_group_id(client, store):
    _setup_group(store)
    resp = client.post("/api/calls/notify", headers=_auth("alice"), json={})
    assert resp.status_code == 422


def test_notify_unknown_group_returns_404(client):
    resp = client.post(
        "/api/calls/notify",
        headers=_auth("alice"),
        json={"group_id": "ghost"},
    )
    assert resp.status_code == 404


def test_notify_non_member_returns_403(client, store, pusher):
    _setup_group(store)
    resp = client.post(
        "/api/calls/notify",
        headers=_auth("eve"),  # eve isn't a member
        json={"group_id": "g1"},
    )
    assert resp.status_code == 403
    pusher.push.assert_not_called()


def test_notify_solo_group_does_not_push(client, store, pusher):
    """Lonely caller — only member of the group. notified=0, no FCM calls."""
    store.create_group(Group(
        group_id="g1", name="Solo", creator_id="alice",
        join_code="X", members={"alice"},
    ))
    store.upsert_user(User(user_id="alice", name="Alice"))
    resp = client.post(
        "/api/calls/notify",
        headers=_auth("alice"),
        json={"group_id": "g1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["notified"] == 0
    pusher.push.assert_not_called()
