from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Generator(ABC):
    @abstractmethod
    async def prepare(self, prompt: str, bpm: float, **conditioning: Any) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def update_conditioning(self, prompt: str, **conditioning: Any) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    async def render(self, path: Path, duration_seconds: float) -> Path:
        raise NotImplementedError

