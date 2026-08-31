from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Analyzer(ABC):
    @abstractmethod
    def analyse(self, path: Path) -> dict[str, Any]: ...

