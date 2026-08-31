from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from dj.models import utc_now


class FeedbackKind(StrEnum):
    LOVE = "love"
    DISLIKE = "dislike"
    MORE_ENERGY = "more-energy"
    LESS_ENERGY = "less-energy"
    BORING = "boring"
    WEIRD = "weird"


class Observation(BaseModel):
    id: str = Field(default_factory=lambda: f"obs-{uuid4().hex}")
    source: str
    kind: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationSource(Protocol):
    async def observe(self) -> list[Observation]: ...


def manual_feedback(kind: FeedbackKind) -> Observation:
    return Observation(source="human", kind=kind.value, value=True, confidence=1.0)


class ObservationStore:
    """Source-neutral append-only input boundary."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: Observation) -> Observation:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json() + "\n")
        return observation

    def read(self) -> list[Observation]:
        if not self.path.exists():
            return []
        return [Observation.model_validate(json.loads(line)) for line in self.path.read_text().splitlines() if line]
