from app.store import (
    Group,
    InMemoryStore,
    Message,
    User,
    new_group_id,
    new_join_code,
)


def test_upsert_user_inserts_then_updates_name():
    store = InMemoryStore()
    user = store.upsert_user(User(user_id="233200000001"))
    assert user.user_id == "233200000001"
    assert store.get_user("233200000001") is user

    updated = store.upsert_user(User(user_id="233200000001", name="Ama"))
    assert updated.name == "Ama"
    assert store.get_user("233200000001").name == "Ama"


def test_upsert_user_does_not_blank_name_with_empty():
    store = InMemoryStore()
    store.upsert_user(User(user_id="u", name="Kojo"))
    store.upsert_user(User(user_id="u", name=""))
    assert store.get_user("u").name == "Kojo"


def test_create_and_lookup_group_by_code():
    store = InMemoryStore()
    g = Group(
        group_id=new_group_id(),
        name="CS401 Study",
        creator_id="u1",
        join_code=new_join_code(),
        members={"u1"},
    )
    store.create_group(g)

    assert store.get_group(g.group_id).name == "CS401 Study"
    assert store.get_group_by_code(g.join_code).group_id == g.group_id


def test_add_member_appends_to_group():
    store = InMemoryStore()
    g = Group(group_id="g1", name="x", creator_id="u1", join_code="C", members={"u1"})
    store.create_group(g)
    updated = store.add_member("g1", "u2")
    assert updated is not None
    assert {"u1", "u2"} <= updated.members


def test_delete_group_removes_code_index():
    store = InMemoryStore()
    g = Group(group_id="g1", name="x", creator_id="u1", join_code="CODE", members=set())
    store.create_group(g)
    assert store.delete_group("g1") is True
    assert store.get_group("g1") is None
    assert store.get_group_by_code("CODE") is None
    assert store.delete_group("g1") is False  # idempotent


def test_messages_are_appended_and_returned_in_order():
    store = InMemoryStore()
    store.append_message(Message(session_key="s", user_id="u", direction="in", text="hi"))
    store.append_message(Message(session_key="s", user_id="u", direction="out", text="hello"))
    msgs = store.recent_messages("s")
    assert [m.text for m in msgs] == ["hi", "hello"]
    assert [m.direction for m in msgs] == ["in", "out"]


def test_recent_messages_respects_limit():
    store = InMemoryStore()
    for i in range(5):
        store.append_message(Message(session_key="s", user_id="u", direction="in", text=str(i)))
    msgs = store.recent_messages("s", limit=2)
    assert [m.text for m in msgs] == ["3", "4"]
