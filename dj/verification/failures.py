from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from typing import Any

import numpy as np
import soundfile as sf

from dj.agent import AgentController
from dj.config import settings
from dj.mixer.supercollider import SuperColliderMixer
from dj.runtime import RuntimeController
from dj.session import SessionStore
from dj.verification.audio import dbfs, longest_silence


def _free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_http(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/snapshot"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("web control surface did not become ready")


def verify_failure_matrix() -> dict[str, Any]:
    """Exercise disposable process failures around one uninterrupted audio graph."""
    store = SessionStore()
    runtime = RuntimeController(store)
    agent = AgentController()
    if runtime.status()["running"] or agent.status()["running"]:
        return {"ok": False, "error": "refusing to disturb an active runtime or agent"}

    previous = store.current_id()
    session_id = f"verify-failures-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    store.create(session_id)
    render = store.root / session_id / "renders" / "failure-matrix.wav"
    web: subprocess.Popen[bytes] | None = None
    recording = False
    checks: dict[str, bool] = {}
    live_status: dict[str, Any] = {}
    try:
        runtime.start(test_mode=True)
        mixer = SuperColliderMixer()
        mixer.record("start", render)
        recording = True
        time.sleep(0.25)

        port = _free_loopback_port()
        web = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "dj.web_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "error",
            ],
            cwd=settings.project_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _wait_for_http(port)
        checks["ui_started"] = web.poll() is None
        web.terminate()
        web.wait(timeout=5)
        checks["ui_failure_audio_continues"] = runtime.status()["running"]

        agent.start(test_mode=True)
        checks["agent_started"] = agent.status()["running"]
        agent.stop()
        checks["agent_failure_audio_continues"] = runtime.status()["running"]

        # No MRT2 UGen/model exists in test mode. Enabling its silent bus is a
        # deterministic generator/model failure; the guard must never leave fallback.
        mixer.stream_enable(True)
        time.sleep(2.4)
        live_status = runtime.status()["stream"]
        checks["missing_model_uses_fallback"] = bool(
            live_status.get("fallback_active")
            and not live_status.get("stream_active")
            and not live_status.get("healthy")
        )
        checks["generator_silence_audio_continues"] = runtime.status()["running"]
        mixer.stream_force_fallback(True)
        time.sleep(0.35)

        mixer.record("stop")
        recording = False
        time.sleep(0.3)
        runtime.stop()
    finally:
        if web is not None and web.poll() is None:
            web.terminate()
            try:
                web.wait(timeout=3)
            except subprocess.TimeoutExpired:
                web.kill()
                web.wait(timeout=3)
        agent.stop()
        if recording:
            SuperColliderMixer().record("stop")
            time.sleep(0.2)
        runtime.stop()
        if previous is None:
            store.current_file.unlink(missing_ok=True)
        else:
            store.current_file.write_text(previous, encoding="utf-8")

    if not render.exists():
        return {"ok": False, "checks": checks, "error": "failure render missing"}
    audio, sample_rate = sf.read(render, always_2d=True, dtype="float32")
    active_audio = audio[int(0.1 * sample_rate) :]
    peak = float(np.max(np.abs(active_audio)))
    silence_ms = longest_silence(active_audio, sample_rate)
    checks.update(
        {
            "finite_post_master_audio": bool(np.isfinite(active_audio).all()),
            "post_master_audio_present": float(np.sqrt(np.mean(np.square(active_audio)))) > 1e-4,
            "post_master_no_clipping": peak <= 0.891,
            "music_did_not_stop": silence_ms < 10,
        }
    )
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "render": str(render),
        "duration_seconds": len(audio) / sample_rate,
        "peak_dbfs": dbfs(peak),
        "longest_silence_ms": silence_ms,
        "stream_failure_status": live_status,
        "checks": checks,
    }
