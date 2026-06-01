import pytest

from app import create_app
from app.auth import issue_jwt
from app.store import InMemoryStore, User


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


def _token(user_id: str) -> str:
    return issue_jwt(user_id=user_id, secret=JWT_SECRET, ttl_days=1)


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


# ----- Users ---------------------------------------------------------
def test_get_unknown_user_404(client):
    resp = client.get("/api/users/u-missing", headers=_auth("u-missing"))
    assert resp.status_code == 404


def test_patch_user_creates_then_updates(client):
    resp = client.patch("/api/users/u1", json={"name": "Ama"}, headers=_auth("u1"))
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Ama"

    resp = client.patch("/api/users/u1", json={"name": "Kojo"}, headers=_auth("u1"))
    assert resp.get_json()["name"] == "Kojo"


def test_list_user_groups_starts_empty(client, store):
    store.upsert_user(User(user_id="u1"))
    resp = client.get("/api/users/u1/groups", headers=_auth("u1"))
    assert resp.status_code == 200
    assert resp.get_json() == {"groups": []}


# ----- Groups --------------------------------------------------------
def test_create_group_requires_name_and_creator(client):
    resp = client.post("/api/groups", json={"name": "x"}, headers=_auth("u1"))
    assert resp.status_code == 422


def test_create_group_returns_201_with_join_code(client):
    resp = client.post(
        "/api/groups",
        json={"name": "CS401", "creator_id": "u1"},
        headers=_auth("u1"),
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "CS401"
    assert body["creator_id"] == "u1"
    assert body["join_code"]
    assert "u1" in body["members"]


def test_get_unknown_group_404(client):
    resp = client.get("/api/groups/nope", headers=_auth("u1"))
    assert resp.status_code == 404


def test_delete_requires_creator(client):
    created = client.post(
        "/api/groups", json={"name": "x", "creator_id": "u1"}, headers=_auth("u1")
    ).get_json()
    gid = created["group_id"]

    # Non-creator tries to delete
    resp = client.delete(f"/api/groups/{gid}", headers=_auth("u2"))
    assert resp.status_code == 403

    resp = client.delete(f"/api/groups/{gid}", headers=_auth("u1"))
    assert resp.status_code == 204
    assert client.get(f"/api/groups/{gid}", headers=_auth("u1")).status_code == 404


def test_join_with_bad_code_returns_404(client):
    resp = client.post(
        "/api/groups/join",
        json={"code": "NOPE", "user_id": "u9"},
        headers=_auth("u9"),
    )
    assert resp.status_code == 404


def test_join_then_listed_under_user_groups(client):
    created = client.post(
        "/api/groups", json={"name": "x", "creator_id": "u1"}, headers=_auth("u1")
    ).get_json()
    code = created["join_code"]

    resp = client.post(
        "/api/groups/join",
        json={"code": code, "user_id": "u2"},
        headers=_auth("u2"),
    )
    assert resp.status_code == 200
    assert set(resp.get_json()["members"]) == {"u1", "u2"}

    listed = client.get("/api/users/u2/groups", headers=_auth("u2")).get_json()["groups"]
    assert len(listed) == 1
    assert listed[0]["group_id"] == created["group_id"]


# ----- Messages ------------------------------------------------------
def test_user_messages_default_empty(client):
    resp = client.get("/api/users/u-nobody/messages", headers=_auth("u-nobody"))
    assert resp.status_code == 200
    assert resp.get_json() == {"messages": []}


def test_group_messages_404_for_unknown_group(client):
    resp = client.get("/api/groups/nope/messages", headers=_auth("u1"))
    assert resp.status_code == 404


def test_group_messages_requires_membership(client, store):
    created = client.post(
        "/api/groups", json={"name": "x", "creator_id": "u1"}, headers=_auth("u1")
    ).get_json()
    resp = client.get(f"/api/groups/{created['group_id']}/messages", headers=_auth("u2"))
    assert resp.status_code == 403


def test_webhook_then_api_round_trip(client, store):
    wa_payload = {
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
    client.post("/webhooks/whatsapp", json=wa_payload)

    msgs = client.get(
        "/api/users/233200000099/messages", headers=_auth("233200000099")
    ).get_json()["messages"]
    assert [m["direction"] for m in msgs] == ["in", "out"]
    assert msgs[0]["text"] == "library hours?"

    user = client.get("/api/users/233200000099", headers=_auth("233200000099")).get_json()
    assert user["user_id"] == "233200000099"


def test_limit_param_is_clamped(client, store):
    from app.store import Message

    for i in range(10):
        store.append_message(Message(session_key="s", user_id="u", direction="in", text=str(i)))

    resp = client.get("/api/users/s/messages?limit=3", headers=_auth("s"))
    assert len(resp.get_json()["messages"]) == 3

    resp = client.get("/api/users/s/messages?limit=garbage", headers=_auth("s"))
    assert len(resp.get_json()["messages"]) == 10


def test_list_groups_for_user_filters_correctly(client, store):
    g1 = client.post(
        "/api/groups", json={"name": "A", "creator_id": "u1"}, headers=_auth("u1")
    ).get_json()
    client.post(
        "/api/groups", json={"name": "B", "creator_id": "u2"}, headers=_auth("u2")
    )
    client.post(
        "/api/groups/join",
        json={"code": g1["join_code"], "user_id": "u3"},
        headers=_auth("u3"),
    )

    u1_groups = client.get("/api/users/u1/groups", headers=_auth("u1")).get_json()["groups"]
    u3_groups = client.get("/api/users/u3/groups", headers=_auth("u3")).get_json()["groups"]

    assert {g["name"] for g in u1_groups} == {"A"}
    assert {g["name"] for g in u3_groups} == {"A"}


def test_create_group_rejects_mismatched_creator(client):
    resp = client.post(
        "/api/groups",
        json={"name": "x", "creator_id": "u1"},
        headers=_auth("u2"),
    )
    assert resp.status_code == 403
