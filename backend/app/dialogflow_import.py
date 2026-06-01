"""Idempotent Dialogflow ES intent importer.

Reads `knowledge_base/dialogflow_intents.json` for display_names + training
phrases and `knowledge_base/faqs.json` for the canonical answer text, then
upserts each intent into the configured Dialogflow agent.

Run via `backend/scripts/import_dialogflow_intents.py` after configuring
`DIALOGFLOW_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_INTENTS_PATH = (
    Path(__file__).resolve().parent.parent / "knowledge_base" / "dialogflow_intents.json"
)
DEFAULT_FAQS_PATH = (
    Path(__file__).resolve().parent.parent / "knowledge_base" / "faqs.json"
)


@dataclass(frozen=True)
class IntentSpec:
    display_name: str
    training_phrases: tuple[str, ...]
    messages: tuple[str, ...]


@dataclass
class ImportReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    planned_create: list[str] = field(default_factory=list)
    planned_update: list[str] = field(default_factory=list)


def load_intent_specs(
    intents_path: Path = DEFAULT_INTENTS_PATH,
    faqs_path: Path = DEFAULT_FAQS_PATH,
) -> list[IntentSpec]:
    """Build IntentSpec list from the two source files.

    The Dialogflow `messages` are sourced from `faqs.json` so the agent's
    fulfillment_text stays in lockstep with what the chatbot serves from the KB.
    Raises ValueError if either file references an intent the other lacks —
    drift between the two would silently break the runtime fallback path.
    """
    intents_data = json.loads(intents_path.read_text(encoding="utf-8"))
    faqs_data = json.loads(faqs_path.read_text(encoding="utf-8"))

    faqs_by_intent = {item["intent"]: item["answer"] for item in faqs_data}
    intent_names = {i["display_name"] for i in intents_data.get("intents", [])}

    missing_in_faqs = intent_names - faqs_by_intent.keys()
    if missing_in_faqs:
        raise ValueError(
            f"Intents present in dialogflow_intents.json but missing in faqs.json: "
            f"{sorted(missing_in_faqs)}"
        )
    missing_in_intents = faqs_by_intent.keys() - intent_names
    if missing_in_intents:
        raise ValueError(
            f"Intents present in faqs.json but missing in dialogflow_intents.json: "
            f"{sorted(missing_in_intents)}"
        )

    specs: list[IntentSpec] = []
    for intent in intents_data["intents"]:
        name = intent["display_name"]
        phrases = tuple(intent.get("training_phrases", []))
        if not phrases:
            raise ValueError(f"Intent {name!r} has no training phrases")
        specs.append(IntentSpec(
            display_name=name,
            training_phrases=phrases,
            messages=(faqs_by_intent[name],),
        ))
    return specs


def load_language_code(intents_path: Path = DEFAULT_INTENTS_PATH) -> str:
    data = json.loads(intents_path.read_text(encoding="utf-8"))
    return data.get("language_code", "en")


def plan_upserts(
    specs: list[IntentSpec],
    existing_display_names: set[str],
) -> tuple[list[IntentSpec], list[IntentSpec]]:
    """Split specs into (to_create, to_update) based on what already exists."""
    to_create = [s for s in specs if s.display_name not in existing_display_names]
    to_update = [s for s in specs if s.display_name in existing_display_names]
    return to_create, to_update


def run_import(
    project_id: str,
    *,
    intents_path: Path = DEFAULT_INTENTS_PATH,
    faqs_path: Path = DEFAULT_FAQS_PATH,
    language: str | None = None,
    dry_run: bool = False,
    client=None,
    dialogflow_module=None,
) -> ImportReport:
    """Upsert every intent in `intents_path` into the Dialogflow agent.

    `client` and `dialogflow_module` are seams for testing — production code
    leaves them None so the real google-cloud-dialogflow library is used.
    """
    specs = load_intent_specs(intents_path, faqs_path)
    lang = language or load_language_code(intents_path)

    # Offline dry-run: don't initialise a real client (which would demand
    # ADC credentials). Report every spec as "would create" — we cannot
    # distinguish create vs update without contacting the agent.
    if dry_run and client is None and dialogflow_module is None:
        return ImportReport(
            planned_create=[s.display_name for s in specs],
            planned_update=[],
        )

    if dialogflow_module is None:
        from google.cloud import dialogflow_v2 as dialogflow_module  # type: ignore
    if client is None:
        client = dialogflow_module.IntentsClient()

    parent = f"projects/{project_id}/agent"
    existing = {
        intent.display_name: intent
        for intent in client.list_intents(
            request={
                "parent": parent,
                "intent_view": dialogflow_module.IntentView.INTENT_VIEW_FULL,
                "language_code": lang,
            }
        )
    }

    to_create, to_update = plan_upserts(specs, set(existing.keys()))
    report = ImportReport(
        planned_create=[s.display_name for s in to_create],
        planned_update=[s.display_name for s in to_update],
    )

    if dry_run:
        return report

    for spec in to_create:
        client.create_intent(
            request={
                "parent": parent,
                "intent": _build_intent_payload(spec, dialogflow_module),
                "language_code": lang,
            }
        )
        report.created.append(spec.display_name)

    for spec in to_update:
        payload = _build_intent_payload(spec, dialogflow_module)
        payload.name = existing[spec.display_name].name
        client.update_intent(
            request={"intent": payload, "language_code": lang}
        )
        report.updated.append(spec.display_name)

    return report


def _build_intent_payload(spec: IntentSpec, dialogflow):
    return dialogflow.Intent(
        display_name=spec.display_name,
        training_phrases=[
            dialogflow.Intent.TrainingPhrase(
                parts=[dialogflow.Intent.TrainingPhrase.Part(text=phrase)],
                type_=dialogflow.Intent.TrainingPhrase.Type.EXAMPLE,
            )
            for phrase in spec.training_phrases
        ],
        messages=[
            dialogflow.Intent.Message(
                text=dialogflow.Intent.Message.Text(text=list(spec.messages))
            )
        ],
    )
