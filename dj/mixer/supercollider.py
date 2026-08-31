from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pythonosc.udp_client import SimpleUDPClient

from dj.config import settings
from dj.mixer.base import MixerBackend
from dj.models import DeckName


class SuperColliderMixer(MixerBackend):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.audio.osc_host
        self.port = port or settings.audio.osc_port
        self.client = SimpleUDPClient(self.host, self.port)

    def _set(self, parameter: str, value: float) -> None:
        self.client.send_message("/agent-dj/set", [parameter, float(value)])

    def set_gain(self, deck: DeckName, gain_db: float) -> None:
        linear = 10 ** (gain_db / 20)
        self._set(f"gain{deck.value}", linear)

    def set_filter(self, deck: DeckName, kind: str, frequency_hz: float) -> None:
        if not math.isfinite(frequency_hz) or frequency_hz <= 0:
            raise ValueError("frequency must be positive and finite")
        names = {"lowpass": "lowpass", "highpass": "highpass"}
        if kind not in names:
            raise ValueError(f"unsupported filter: {kind}")
        self._set(f"{names[kind]}{deck.value}", frequency_hz)

    def crossfade(self, target: DeckName, duration_seconds: float) -> None:
        position = -1.0 if target is DeckName.A else 1.0
        self.client.send_message(
            "/agent-dj/crossfade", [position, max(0.01, float(duration_seconds))]
        )

    def load(self, deck: DeckName, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
        self.client.send_message("/agent-dj/load", [deck.value, str(path.resolve())])

    def record(self, action: str, path: Path | None = None) -> None:
        if action not in {"start", "stop"}:
            raise ValueError("record action must be start or stop")
        self.client.send_message(
            "/agent-dj/record", [action, str(path.resolve()) if path is not None else ""]
        )

    def status(self) -> dict[str, Any]:
        ready = settings.sessions_dir / ".runtime-ready"
        return {"ok": ready.exists(), "backend": "supercollider", "port": self.port}

    def quit(self) -> None:
        self.client.send_message("/agent-dj/quit", [])

