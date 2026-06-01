import json
import types
from pathlib import Path

import pytest

from app.dialogflow_import import (
    DEFAULT_FAQS_PATH,
    DEFAULT_INTENTS_PATH,
    IntentSpec,
    load_intent_specs,
    plan_upserts,
    run_import,
)


# ---------- repo-state guard ---------------------------------------------
def test_repo_kb_and_intents_are_in_sync():
    """Every intent in the canonical files must round-trip cleanly."""
    specs = load_intent_specs()  # raises on drift
    intent_names = {s.display_name for s in specs}
    assert intent_names, "no intents loaded — KB sources empty?"
    # Spot-check the seed set so we notice if anyone deletes one by accident.
    assert {"library.hours", "exam.schedule"}.issubset(intent_names)


# ---------- load_intent_specs --------------------------------------------
def _write(tmp_path: Path, intents: list[dict], faqs: list[dict]):
    intents_path = tmp_path / "intents.json"
    faqs_path = tmp_path / "faqs.json"
    intents_path.write_text(
        json.dumps({"language_code": "en", "intents": intents}), encoding="utf-8"
    )
    faqs_path.write_text(json.dumps(faqs), encoding="utf-8")
    return intents_path, faqs_path


def test_load_intent_specs_pairs_answers_with_phrases(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[
            {"display_name": "x.y", "training_phrases": ["a", "b"]},
        ],
        faqs=[{"intent": "x.y", "answer": "ANSWER"}],
    )
    specs = load_intent_specs(intents_path, faqs_path)
    assert specs == [IntentSpec("x.y", ("a", "b"), ("ANSWER",))]


def test_load_intent_specs_rejects_orphan_intent(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[{"display_name": "x.y", "training_phrases": ["a"]}],
        faqs=[],
    )
    with pytest.raises(ValueError, match="missing in faqs.json"):
        load_intent_specs(intents_path, faqs_path)


def test_load_intent_specs_rejects_orphan_faq(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[],
        faqs=[{"intent": "x.y", "answer": "ANSWER"}],
    )
    with pytest.raises(ValueError, match="missing in dialogflow_intents.json"):
        load_intent_specs(intents_path, faqs_path)


def test_load_intent_specs_rejects_empty_phrases(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[{"display_name": "x.y", "training_phrases": []}],
        faqs=[{"intent": "x.y", "answer": "ANSWER"}],
    )
    with pytest.raises(ValueError, match="no training phrases"):
        load_intent_specs(intents_path, faqs_path)


# ---------- plan_upserts -------------------------------------------------
def test_plan_upserts_splits_by_existence():
    specs = [IntentSpec("a", ("x",), ("ans",)), IntentSpec("b", ("y",), ("ans",))]
    to_create, to_update = plan_upserts(specs, {"a"})
    assert [s.display_name for s in to_create] == ["b"]
    assert [s.display_name for s in to_update] == ["a"]


# ---------- run_import with a mocked dialogflow module ------------------
class _FakeIntent:
    def __init__(self, display_name=None, name=None, **kwargs):
        self.display_name = display_name
        self.name = name
        self.kwargs = kwargs


class _FakeTrainingPhrase:
    class Type:
        EXAMPLE = "EXAMPLE"

    class Part:
        def __init__(self, text=None):
            self.text = text

    def __init__(self, parts=None, type_=None):
        self.parts = parts
        self.type_ = type_


class _FakeMessage:
    class Text:
        def __init__(self, text=None):
            self.text = text

    def __init__(self, text=None):
        self.text = text


_FakeIntent.TrainingPhrase = _FakeTrainingPhrase
_FakeIntent.Message = _FakeMessage


class _FakeIntentView:
    INTENT_VIEW_FULL = "FULL"


def _fake_dialogflow_module():
    mod = types.SimpleNamespace()
    mod.Intent = _FakeIntent
    mod.IntentView = _FakeIntentView
    return mod


class _FakeClient:
    def __init__(self, existing: list[_FakeIntent]):
        self._existing = existing
        self.created: list = []
        self.updated: list = []
        self.list_calls: list = []

    def list_intents(self, request):
        self.list_calls.append(request)
        return list(self._existing)

    def create_intent(self, request):
        self.created.append(request)

    def update_intent(self, request):
        self.updated.append(request)


def test_run_import_creates_when_agent_is_empty(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[
            {"display_name": "x.y", "training_phrases": ["phrase one"]},
            {"display_name": "p.q", "training_phrases": ["phrase two"]},
        ],
        faqs=[
            {"intent": "x.y", "answer": "ANS1"},
            {"intent": "p.q", "answer": "ANS2"},
        ],
    )
    client = _FakeClient(existing=[])
    report = run_import(
        project_id="proj",
        intents_path=intents_path,
        faqs_path=faqs_path,
        client=client,
        dialogflow_module=_fake_dialogflow_module(),
    )

    assert sorted(report.created) == ["p.q", "x.y"]
    assert report.updated == []
    assert {c["intent"].display_name for c in client.created} == {"x.y", "p.q"}
    assert all(c["parent"] == "projects/proj/agent" for c in client.created)
    assert all(c["language_code"] == "en" for c in client.created)


def test_run_import_updates_existing_and_creates_new(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[
            {"display_name": "x.y", "training_phrases": ["phrase one"]},
            {"display_name": "p.q", "training_phrases": ["phrase two"]},
        ],
        faqs=[
            {"intent": "x.y", "answer": "ANS1"},
            {"intent": "p.q", "answer": "ANS2"},
        ],
    )
    existing = [
        _FakeIntent(display_name="x.y", name="projects/proj/agent/intents/uuid-xy"),
    ]
    client = _FakeClient(existing=existing)

    report = run_import(
        project_id="proj",
        intents_path=intents_path,
        faqs_path=faqs_path,
        client=client,
        dialogflow_module=_fake_dialogflow_module(),
    )

    assert report.created == ["p.q"]
    assert report.updated == ["x.y"]
    # Update carries the existing intent's resource name
    assert client.updated[0]["intent"].name == "projects/proj/agent/intents/uuid-xy"
    assert client.created[0]["intent"].display_name == "p.q"


def test_run_import_dry_run_writes_nothing(tmp_path):
    intents_path, faqs_path = _write(
        tmp_path,
        intents=[{"display_name": "x.y", "training_phrases": ["a"]}],
        faqs=[{"intent": "x.y", "answer": "ANS"}],
    )
    client = _FakeClient(existing=[])
    report = run_import(
        project_id="proj",
        intents_path=intents_path,
        faqs_path=faqs_path,
        dry_run=True,
        client=client,
        dialogflow_module=_fake_dialogflow_module(),
    )
    assert report.planned_create == ["x.y"]
    assert report.created == []
    assert client.created == []
    assert client.updated == []


def test_run_import_uses_language_from_file_when_not_overridden(tmp_path):
    intents_path = tmp_path / "intents.json"
    faqs_path = tmp_path / "faqs.json"
    intents_path.write_text(
        json.dumps({
            "language_code": "fr",
            "intents": [{"display_name": "x", "training_phrases": ["a"]}],
        }),
        encoding="utf-8",
    )
    faqs_path.write_text(
        json.dumps([{"intent": "x", "answer": "ANS"}]),
        encoding="utf-8",
    )
    client = _FakeClient(existing=[])
    run_import(
        project_id="proj",
        intents_path=intents_path,
        faqs_path=faqs_path,
        client=client,
        dialogflow_module=_fake_dialogflow_module(),
    )
    assert client.list_calls[0]["language_code"] == "fr"
    assert client.created[0]["language_code"] == "fr"
