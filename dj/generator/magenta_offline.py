from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from dj.config import settings
from dj.generator.base import Generator


class MagentaOfflineGenerator(Generator):
    """Native MLX MRT2 adapter for bounded local renders.

    Model imports are intentionally lazy so deterministic development and the live audio
    runtime do not depend on ML packages being installed.
    """

    def __init__(self, model_name: str = "mrt2_small") -> None:
        self.model_name = model_name
        self.prompt = ""
        self.bpm = 124.0
        self.running = False
        self._model: Any | None = None
        self._embedding: Any | None = None
        self._conditioning_key: str | None = None
        self.last_metrics: dict[str, Any] = {}

    def _load(self) -> None:
        if self._model is not None:
            return
        from magenta_rt import MagentaRT2StdMlxfn, paths
        from magenta_rt.config import MUSICCOCA

        paths.set_magenta_home(settings.models_dir)
        started = time.monotonic()
        self._model = MagentaRT2StdMlxfn(size=self.model_name)
        self._conditioning_key = MUSICCOCA.key
        self.last_metrics["load_seconds"] = time.monotonic() - started

    async def prepare(self, prompt: str, bpm: float, **conditioning: Any) -> None:
        self._load()
        self.prompt = prompt
        self.bpm = bpm
        assert self._model is not None
        started = time.monotonic()
        self._embedding = self._model.embed_style(prompt, use_mapper=True)
        self.last_metrics["embedding_seconds"] = time.monotonic() - started

    async def start(self) -> None:
        self.running = True

    async def update_conditioning(self, prompt: str, **conditioning: Any) -> None:
        if self._model is None:
            await self.prepare(prompt, self.bpm, **conditioning)
            return
        self.prompt = prompt
        started = time.monotonic()
        self._embedding = self._model.embed_style(prompt, use_mapper=True)
        self.last_metrics["embedding_seconds"] = time.monotonic() - started

    async def stop(self) -> None:
        self.running = False

    async def health(self) -> dict[str, Any]:
        model_path = settings.models_dir / "models" / self.model_name / f"{self.model_name}.mlxfn"
        return {
            "ok": model_path.exists(),
            "backend": "magenta-mlx-offline",
            "model": self.model_name,
            "loaded": self._model is not None,
            "running": self.running,
            "local_only": True,
            "model_path": str(model_path),
            **self.last_metrics,
        }

    async def render(self, path: Path, duration_seconds: float) -> Path:
        if duration_seconds <= 0:
            raise ValueError("duration must be positive")
        if self._model is None or self._embedding is None or self._conditioning_key is None:
            raise RuntimeError("prepare must be called before render")
        frames = max(1, round(duration_seconds * 25))
        started = time.monotonic()
        wav, _state = self._model.generate(
            conditioning={self._conditioning_key: self._embedding}, frames=frames
        )
        elapsed = time.monotonic() - started
        path.parent.mkdir(parents=True, exist_ok=True)
        wav.write(str(path))
        actual_duration = frames / 25
        self.last_metrics.update(
            {
                "generated_seconds": actual_duration,
                "wall_seconds": elapsed,
                "realtime_factor": elapsed / actual_duration,
                "steps_per_second": frames / elapsed,
            }
        )
        return path

