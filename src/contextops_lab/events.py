"""Append-only JSONL event storage."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RequestEvent


class JsonlEventStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: RequestEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
