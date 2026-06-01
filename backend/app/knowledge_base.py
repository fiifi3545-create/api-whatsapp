from __future__ import annotations

import json
from pathlib import Path

DEFAULT_KB_PATH = Path(__file__).resolve().parent.parent / "knowledge_base" / "faqs.json"


class KnowledgeBase:
    def __init__(self, entries: dict[str, str]):
        self._entries = entries

    @classmethod
    def load_default(cls) -> "KnowledgeBase":
        return cls.load(DEFAULT_KB_PATH)

    @classmethod
    def load(cls, path: Path) -> "KnowledgeBase":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls({item["intent"]: item["answer"] for item in data})

    def answer_for_intent(self, intent: str) -> str | None:
        return self._entries.get(intent)

    def intents(self) -> list[str]:
        return list(self._entries.keys())
