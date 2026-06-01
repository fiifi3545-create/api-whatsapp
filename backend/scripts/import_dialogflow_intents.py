#!/usr/bin/env python
"""CLI: import knowledge_base/dialogflow_intents.json into a Dialogflow ES agent.

Usage:
    # uses DIALOGFLOW_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS from env / .env
    python backend/scripts/import_dialogflow_intents.py

    # override project and dry-run
    python backend/scripts/import_dialogflow_intents.py \\
        --project-id my-gcp-project --dry-run

The script is idempotent: it lists existing intents in the agent and updates
ones whose display_name already exists, only creating new intents otherwise.
Safe to re-run after editing knowledge_base/dialogflow_intents.json or
knowledge_base/faqs.json.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make `app.*` importable when the script is run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app.dialogflow_import import (  # noqa: E402
    DEFAULT_FAQS_PATH,
    DEFAULT_INTENTS_PATH,
    run_import,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project-id",
        default=os.environ.get("DIALOGFLOW_PROJECT_ID", ""),
        help="GCP project hosting the Dialogflow ES agent (env: DIALOGFLOW_PROJECT_ID).",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("DIALOGFLOW_LANGUAGE_CODE", ""),
        help="Override the language code (defaults to the value in the JSON file).",
    )
    parser.add_argument(
        "--intents-path",
        type=Path,
        default=DEFAULT_INTENTS_PATH,
        help=f"Path to dialogflow_intents.json (default: {DEFAULT_INTENTS_PATH}).",
    )
    parser.add_argument(
        "--faqs-path",
        type=Path,
        default=DEFAULT_FAQS_PATH,
        help=f"Path to faqs.json (default: {DEFAULT_FAQS_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without calling Dialogflow.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.project_id:
        print(
            "error: --project-id (or DIALOGFLOW_PROJECT_ID) is required",
            file=sys.stderr,
        )
        return 2
    if not args.dry_run and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print(
            "error: GOOGLE_APPLICATION_CREDENTIALS must point at a service-account JSON",
            file=sys.stderr,
        )
        return 2

    report = run_import(
        project_id=args.project_id,
        intents_path=args.intents_path,
        faqs_path=args.faqs_path,
        language=args.language or None,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("DRY RUN — no changes applied")
        print(f"  would create: {report.planned_create or '(none)'}")
        print(f"  would update: {report.planned_update or '(none)'}")
    else:
        print(f"created: {report.created or '(none)'}")
        print(f"updated: {report.updated or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
