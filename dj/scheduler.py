from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dj.models import DJState
from dj.transport import Transport


def current_bar(state: DJState, now: datetime | None = None) -> float:
    if not state.transport.playing or state.transport.started_at is None:
        return float(state.transport.bar)
    now = now or datetime.now(UTC)
    elapsed = (now - state.transport.started_at).total_seconds()
    return elapsed / Transport(state.transport.bpm).seconds_per_bar


def resolve_bar(expression: str, state: DJState) -> int:
    bar = current_bar(state)
    if expression.startswith("next-"):
        phrase_bars = int(expression.removeprefix("next-"))
        return Transport(state.transport.bpm).next_phrase_bar(bar, phrase_bars)
    if expression.startswith("bar+"):
        return int(bar) + int(expression.removeprefix("bar+"))
    return int(expression)


class ScheduleStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, action: str, target: str, at_bar: int, **parameters: Any) -> dict[str, Any]:
        item = {
            "id": f"schedule-{datetime.now(UTC).timestamp():.6f}",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending",
            "action": action,
            "target": target,
            "at_bar": at_bar,
            "parameters": parameters,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, separators=(",", ":")) + "\n")
        return item

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]

