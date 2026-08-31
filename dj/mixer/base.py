from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from dj.models import DeckName


class MixerBackend(ABC):
    @abstractmethod
    def set_gain(self, deck: DeckName, gain_db: float) -> None: ...

    @abstractmethod
    def set_filter(self, deck: DeckName, kind: str, frequency_hz: float) -> None: ...

    @abstractmethod
    def crossfade(self, target: DeckName, duration_seconds: float) -> None: ...

    @abstractmethod
    def load(self, deck: DeckName, path: Path) -> None: ...

    @abstractmethod
    def record(self, action: str, path: Path | None = None) -> None: ...

    @abstractmethod
    def status(self) -> dict[str, Any]: ...

