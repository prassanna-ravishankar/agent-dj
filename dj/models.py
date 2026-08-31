from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DeckName(StrEnum):
    A = "A"
    B = "B"


class DeckStatus(StrEnum):
    STOPPED = "stopped"
    PREPARING = "preparing"
    PREPARED = "prepared"
    PLAYING = "playing"
    FAILED = "failed"


class TransportState(BaseModel):
    playing: bool = False
    bpm: float = 124.0
    bar: int = 0
    beat: float = 0.0
    started_at: datetime | None = None
    sample_position: int = 0


class DeckState(BaseModel):
    name: DeckName
    status: DeckStatus = DeckStatus.STOPPED
    source: str = "fake"
    prompt: str | None = None
    gain_db: float = -60.0
    energy: float | None = None
    audio_path: str | None = None
    duration_seconds: float | None = None


class MasterState(BaseModel):
    peak_dbfs: float | None = None
    lufs_short: float | None = None
    limiter_reduction_db: float = 0.0


class FutureState(BaseModel):
    covered_until_bar: int = 0
    estimated_seconds: float = 0.0


class DJState(BaseModel):
    session_id: str
    status: str = "development"
    transport: TransportState = Field(default_factory=TransportState)
    decks: dict[DeckName, DeckState] = Field(
        default_factory=lambda: {
            DeckName.A: DeckState(name=DeckName.A),
            DeckName.B: DeckState(name=DeckName.B),
        }
    )
    master: MasterState = Field(default_factory=MasterState)
    future: FutureState = Field(default_factory=FutureState)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
