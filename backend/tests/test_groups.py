from app.groups import GroupService
from app.store import InMemoryStore


def test_create_makes_creator_a_member():
    svc = GroupService(InMemoryStore())
    g = svc.create("CS401", "u1")
    assert g.creator_id == "u1"
    assert "u1" in g.members
    assert g.join_code  # non-empty


def test_join_with_valid_code_adds_member():
    store = InMemoryStore()
    svc = GroupService(store)
    g = svc.create("CS401", "u1")

    joined = svc.join(g.join_code, "u2")
    assert joined is not None
    assert "u2" in joined.members
    assert "u1" in joined.members


def test_join_with_unknown_code_returns_none():
    svc = GroupService(InMemoryStore())
    assert svc.join("NOPE", "u1") is None


def test_delete_only_works_for_creator():
    svc = GroupService(InMemoryStore())
    g = svc.create("CS401", "u1")
    assert svc.delete(g.group_id, "u2") is False
    assert svc.delete(g.group_id, "u1") is True
    assert svc.get(g.group_id) is None


def test_join_codes_are_unique_across_groups():
    svc = GroupService(InMemoryStore())
    codes = {svc.create(f"g{i}", "u").join_code for i in range(20)}
    assert len(codes) == 20
