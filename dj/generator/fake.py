from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.generator.base import Generator


class FakeGenerator(Generator):
    def __init__(self, frequency_hz: float, sample_rate: int = 48_000) -> None:
        self.frequency_hz = frequency_hz
        self.sample_rate = sample_rate
        self.running = False
        self.prompt = ""
        self.bpm = 124.0

    async def prepare(self, prompt: str, bpm: float, **conditioning: Any) -> None:
        self.prompt = prompt
        self.bpm = bpm

    async def start(self) -> None:
        self.running = True

    async def update_conditioning(self, prompt: str, **conditioning: Any) -> None:
        self.prompt = prompt

    async def stop(self) -> None:
        self.running = False

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "running": self.running, "backend": "fake"}

    async def render(self, path: Path, duration_seconds: float) -> Path:
        frames = round(duration_seconds * self.sample_rate)
        time = np.arange(frames, dtype=np.float64) / self.sample_rate
        mono = 0.2 * np.sin(2 * np.pi * self.frequency_hz * time)
        stereo = np.column_stack((mono, mono)).astype(np.float32)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, stereo, self.sample_rate, subtype="FLOAT")
        return path

