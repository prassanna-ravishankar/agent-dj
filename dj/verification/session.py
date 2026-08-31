from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.config import settings
from dj.events import EventLog
from dj.models import DJState
from dj.verification.audio import dbfs, longest_silence, tone_magnitude


def latest_session_id() -> str | None:
    renders = list(settings.sessions_dir.glob("*/renders/master.wav"))
    if not renders:
        return None
    intended = [
        render
        for render in renders
        if any(
            event["type"] == "set_intent"
            for event in EventLog(render.parents[1] / "events.jsonl").read()
        )
    ]
    candidates = intended or renders
    return max(candidates, key=lambda path: path.stat().st_mtime).parents[1].name


def verify_session(session: str = "latest") -> dict[str, Any]:
    session_id = latest_session_id() if session == "latest" else session
    if session_id is None:
        return {"ok": False, "error": "no sessions exist"}
    directory = settings.sessions_dir / session_id
    state_path = directory / "state.json"
    if not state_path.exists():
        return {"ok": False, "error": f"session not found: {session_id}"}
    state = DJState.model_validate_json(state_path.read_text(encoding="utf-8"))
    events = EventLog(directory / "events.jsonl").read()
    types = [event["type"] for event in events]
    render = directory / "renders" / "master.wav"
    if not render.exists():
        return {"ok": False, "session_id": session_id, "error": "master render missing"}
    audio, sample_rate = sf.read(render, always_2d=True, dtype="float32")
    duration = len(audio) / sample_rate
    planned = next(
        (
            float(event["planned_duration_seconds"])
            for event in events
            if event["type"] in {"scripted_set_started", "set_intent"}
        ),
        0.0,
    )
    transition_indices = [index for index, kind in enumerate(types) if kind == "transition_scheduled"]
    state_indices = [index for index, kind in enumerate(types) if kind == "state_inspected"]
    peak = float(np.max(np.abs(audio)))
    checks = {
        "runtime_started": "runtime_started" in types,
        "runtime_stopped": "runtime_stopped" in types,
        "state_inspected_before_changes": bool(
            state_indices and transition_indices and state_indices[0] < transition_indices[0]
        ),
        "transitions_scheduled": len(transition_indices) >= 2,
        "transitions_executed": types.count("schedule_executed") >= 2,
        "future_coverage_safe": state.future.estimated_seconds >= settings.coverage.critical_seconds,
        "no_runtime_errors": "error" not in types,
        "recording_long_enough": duration >= max(1.0, planned - 0.75),
        "finite_audio": bool(np.isfinite(audio).all()),
        "no_clipping": peak <= 0.891,
        "music_did_not_stop": longest_silence(audio, sample_rate) < 100,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "render": str(render),
        "duration_seconds": duration,
        "peak_dbfs": dbfs(peak),
        "longest_silence_ms": longest_silence(audio, sample_rate),
        "checks": checks,
    }


def verify_scripted_audio(path: Path) -> dict[str, Any]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    mono = audio.mean(axis=1)
    duration = len(mono) / sample_rate

    def segment(start: float, end: float) -> np.ndarray:
        return mono[int(start * sample_rate) : int(min(end, duration) * sample_rate)]

    first = segment(0.1, 0.4)
    middle = segment(2.0, 2.6)
    last = segment(max(0, duration - 0.6), duration)
    ratios = {
        "first_a_to_b": tone_magnitude(first, sample_rate, 440)
        / max(tone_magnitude(first, sample_rate, 880), 1e-9),
        "middle_b_to_a": tone_magnitude(middle, sample_rate, 880)
        / max(tone_magnitude(middle, sample_rate, 440), 1e-9),
        "last_a_to_b": tone_magnitude(last, sample_rate, 440)
        / max(tone_magnitude(last, sample_rate, 880), 1e-9),
    }
    return {"ok": all(value > 20 for value in ratios.values()), "frequency_ratios": ratios}
