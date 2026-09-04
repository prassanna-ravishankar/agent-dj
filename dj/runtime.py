from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dj.config import settings
from dj.doctor import find_executable
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckStatus
from dj.session import SessionStore


class RuntimeController:
    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()
        self.ready_file = settings.sessions_dir / ".runtime-ready"
        self.pid_file = settings.sessions_dir / ".runtime-pid"
        self.stream_status_file = settings.sessions_dir / ".stream-status.json"

    def status(self) -> dict[str, Any]:
        pid = self._pid()
        running = bool(pid and self._alive(pid) and self.ready_file.exists())
        return {
            "ok": running,
            "running": running,
            "pid": pid,
            "local_only": True,
            "stream": self._stream_status(running),
        }

    def start(self, test_mode: bool = False, timeout: float = 60.0) -> dict[str, Any]:
        existing = self.status()
        if existing["running"]:
            return existing
        state = self.store.load()
        if not test_mode and not any(
            deck.audio_path and Path(deck.audio_path).exists() for deck in state.decks.values()
        ):
            raise RuntimeError("prepare at least one local audio deck before starting live audio")
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        self.stream_status_file.unlink(missing_ok=True)
        sclang = find_executable("sclang")
        if sclang is None:
            raise RuntimeError("sclang is not installed")
        session_dir = settings.sessions_dir / state.session_id
        log_path = session_dir / "runtime.log"
        bootstrap = settings.project_root / "supercollider" / "bootstrap.scd"
        log = log_path.open("a", encoding="utf-8")
        stream_available = not test_mode and self._stream_available()
        env = os.environ.copy()
        env.update(
            {
                "AGENT_DJ_MRT2_AVAILABLE": "1" if stream_available else "0",
                "AGENT_DJ_MRT2_ASSETS": str(settings.mrt2.assets_dir),
                "AGENT_DJ_MRT2_MODEL": str(settings.mrt2.model_file),
                "AGENT_DJ_MRT2_BUFFER": str(settings.mrt2.buffer_samples),
                "AGENT_DJ_MRT2_THRESHOLD": str(settings.mrt2.signal_threshold),
            }
        )
        process = subprocess.Popen(
            [sclang, str(bootstrap)], cwd=settings.project_root,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=env,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready_file.exists():
                break
            if process.poll() is not None:
                raise RuntimeError(f"SuperCollider exited; inspect {log_path}")
            time.sleep(0.1)
        else:
            process.terminate()
            raise TimeoutError(f"SuperCollider did not become ready; inspect {log_path}")
        state.status = "live"
        state.transport.playing = True
        state.transport.started_at = datetime.now(UTC)
        mixer = SuperColliderMixer()
        for deck_name in ("A", "B"):
            deck = state.decks[deck_name]
            if deck.audio_path and Path(deck.audio_path).exists():
                mixer.load(deck.name, Path(deck.audio_path))
        state.stream.available = stream_available
        state.stream.healthy = False
        state.stream.fallback_active = True
        state.stream.signal_level = None
        state.stream.mix = 0.0
        mixer.stream_temperature(state.stream.temperature)
        mixer.stream_top_k(state.stream.top_k)
        for prompt in state.stream.prompts:
            if prompt.text:
                mixer.stream_prompt(prompt.slot, prompt.text, prompt.weight)
        mixer.stream_force_fallback(state.stream.force_fallback)
        mixer.stream_enable(state.stream.enabled and stream_available)
        state.decks["A"].status = DeckStatus.PLAYING
        state.decks["A"].gain_db = 0
        state.decks["B"].status = DeckStatus.PREPARED
        state.decks["B"].gain_db = -60
        # Looping safe buffers continue without a controller; JSON cannot represent infinity.
        has_safe_audio = test_mode or any(deck.audio_path for deck in state.decks.values())
        state.future.estimated_seconds = 86_400.0 if has_safe_audio else 0
        self.store.save(state)
        self.store.events(state.session_id).append(
            "runtime_started", pid=process.pid, test_mode=test_mode, backend="supercollider",
            stream_available=stream_available, fallback="looping-deck",
        )
        return self.status()

    def stop(self, timeout: float = 8.0) -> dict[str, Any]:
        pid = self._pid()
        if pid is None or not self._alive(pid):
            self.ready_file.unlink(missing_ok=True)
            self.pid_file.unlink(missing_ok=True)
            return {"ok": True, "running": False}
        SuperColliderMixer().quit()
        deadline = time.monotonic() + timeout
        while (
            time.monotonic() < deadline
            and self._alive(pid)
            and self.ready_file.exists()
        ):
            time.sleep(0.1)
        if self._alive(pid) and self.ready_file.exists():
            os.kill(pid, signal.SIGTERM)
        state = self.store.load()
        state.status = "stopped"
        state.transport.playing = False
        state.transport.started_at = None
        self.store.save(state)
        self.store.events(state.session_id).append("runtime_stopped")
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        self.stream_status_file.unlink(missing_ok=True)
        return {"ok": True, "running": False}

    def _stream_available(self) -> bool:
        required = (
            settings.mrt2.extension_dir / "MRT2.scx",
            settings.mrt2.extension_dir / "MRT2.sc",
            settings.mrt2.extension_dir / "mlx.metallib",
            settings.mrt2.assets_dir / "musiccoca" / "spm.model",
            settings.mrt2.model_file,
            settings.mrt2.model_file.with_name(
                f"{settings.mrt2.model_file.stem}_state.safetensors"
            ),
        )
        return all(path.exists() for path in required)

    def _stream_status(self, running: bool) -> dict[str, Any]:
        fallback = {
            "available": self._stream_available(),
            "enabled": False,
            "healthy": False,
            "fallback_active": True,
            "stream_active": False,
            "warming_up": False,
            "signal_detected": False,
            "phase": "disabled",
            "signal_level": None,
            "mix": 0.0,
        }
        if not running or not self.stream_status_file.exists():
            return fallback
        for _ in range(3):
            try:
                stat = self.stream_status_file.stat()
                age = max(0.0, time.time() - stat.st_mtime)
                if age > 2.0:
                    return {
                        **fallback,
                        "enabled": bool(self.store.load().stream.enabled),
                        "phase": "status-stale",
                        "status_stale": True,
                        "heartbeat_age_seconds": age,
                    }
                value = json.loads(self.stream_status_file.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return {
                        **fallback,
                        **value,
                        "status_stale": False,
                        "heartbeat_age_seconds": age,
                        "heartbeat_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    }
            except (OSError, json.JSONDecodeError):
                time.sleep(0.01)
        return fallback

    def _pid(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text().strip())
        except ValueError:
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
