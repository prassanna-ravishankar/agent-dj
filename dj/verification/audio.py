from __future__ import annotations

import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.config import settings
from dj.doctor import find_executable


def dbfs(value: float) -> float:
    return 20 * math.log10(max(abs(value), 1e-12))


def tone_magnitude(samples: np.ndarray, sample_rate: int, frequency: float) -> float:
    if samples.size == 0:
        return 0.0
    window = np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(samples * window))
    frequencies = np.fft.rfftfreq(len(samples), 1 / sample_rate)
    index = int(np.argmin(np.abs(frequencies - frequency)))
    return float(spectrum[index])


def analyse_test_render(path: Path) -> dict[str, Any]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    mono = audio.mean(axis=1)

    def segment(start: float, end: float) -> np.ndarray:
        return mono[int(start * sample_rate) : int(end * sample_rate)]

    before = segment(0.5, 1.5)
    middle = segment(2.8, 3.5)
    after = segment(4.8, 5.5)
    attenuated = segment(6.25, 6.75)
    filtered = segment(7.2, min(7.8, len(mono) / sample_rate))

    before_440 = tone_magnitude(before, sample_rate, 440)
    before_880 = tone_magnitude(before, sample_rate, 880)
    middle_440 = tone_magnitude(middle, sample_rate, 440)
    middle_880 = tone_magnitude(middle, sample_rate, 880)
    after_440 = tone_magnitude(after, sample_rate, 440)
    after_880 = tone_magnitude(after, sample_rate, 880)
    attenuated_rms = float(np.sqrt(np.mean(np.square(attenuated))))
    after_rms = float(np.sqrt(np.mean(np.square(after))))
    filtered_880 = tone_magnitude(filtered, sample_rate, 880)
    attenuated_880 = tone_magnitude(attenuated, sample_rate, 880)
    peak = float(np.max(np.abs(audio)))
    finite = bool(np.isfinite(audio).all())
    longest_silence_ms = longest_silence(audio, sample_rate)

    checks = {
        "a_dominant_before": before_440 > before_880 * 20,
        "both_present_midpoint": middle_440 > 1 and middle_880 > 1,
        "b_dominant_after": after_880 > after_440 * 20,
        "gain_reduction": 0.35 < (attenuated_rms / max(after_rms, 1e-9)) < 0.7,
        "lowpass_attenuation": filtered_880 < attenuated_880 * 0.65,
        "finite_samples": finite,
        "no_clipping": peak <= 0.891,
        "no_unexpected_silence": longest_silence_ms < 100,
    }
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "sample_rate": sample_rate,
        "channels": audio.shape[1],
        "duration_seconds": len(audio) / sample_rate,
        "peak_dbfs": dbfs(peak),
        "longest_silence_ms": longest_silence_ms,
        "checks": checks,
        "measurements": {
            "before_440_to_880": before_440 / max(before_880, 1e-9),
            "after_880_to_440": after_880 / max(after_440, 1e-9),
            "gain_rms_ratio": attenuated_rms / max(after_rms, 1e-9),
            "filter_880_ratio": filtered_880 / max(attenuated_880, 1e-9),
        },
    }


def longest_silence(audio: np.ndarray, sample_rate: int, threshold: float = 1e-5) -> float:
    active = np.max(np.abs(audio), axis=1) >= threshold
    padded = np.concatenate(([True], active, [True]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    silent_lengths = edges[1::2] - edges[::2]
    return float(silent_lengths.max(initial=0) * 1000 / sample_rate)


def render_supercollider_fixture(output: Path, duration: float = 8.0) -> dict[str, Any]:
    sclang = find_executable("sclang")
    if sclang is None:
        return {"ok": False, "error": "sclang not found"}
    script = settings.project_root / "supercollider" / "tests" / "render_mixer.scd"
    env = os.environ.copy()
    env["AGENT_DJ_RENDER"] = str(output)
    env["AGENT_DJ_DURATION"] = str(duration)
    try:
        result = subprocess.run(
            [sclang, str(script)],
            cwd=settings.project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=max(30, duration + 20),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": "SuperCollider render timed out", "stdout": exc.stdout}
    if result.returncode != 0 or not output.exists():
        return {
            "ok": False,
            "error": "SuperCollider render failed",
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    report = analyse_test_render(output)
    report["supercollider_output"] = result.stdout[-1000:]
    return report


def run_sc_render(
    script_name: str,
    output: Path,
    duration: float,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    sclang = find_executable("sclang")
    if sclang is None:
        return {"ok": False, "error": "sclang not found"}
    script = settings.project_root / "supercollider" / "tests" / script_name
    env = os.environ.copy()
    env["AGENT_DJ_RENDER"] = str(output)
    env["AGENT_DJ_DURATION"] = str(duration)
    env.update(extra_env or {})
    try:
        result = subprocess.run(
            [sclang, str(script)], cwd=settings.project_root, env=env,
            capture_output=True, text=True, timeout=max(30, duration + 25), check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SuperCollider render timed out"}
    return {
        "ok": result.returncode == 0 and output.exists(),
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def verify_timing() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agent-dj-timing-") as directory:
        output = Path(directory) / "timing.wav"
        render = run_sc_render("render_timing.scd", output, 3.0)
        if not render["ok"]:
            return render
        audio, sample_rate = sf.read(output, always_2d=True, dtype="float32")
        mono = audio.mean(axis=1)
        frame = max(128, round(sample_rate * 0.005))
        detected: float | None = None
        for start in range(round(1.8 * sample_rate), round(2.2 * sample_rate), frame):
            chunk = mono[start : start + frame]
            if tone_magnitude(chunk, sample_rate, 880) > tone_magnitude(chunk, sample_rate, 440) * 2:
                detected = start / sample_rate
                break
        error_ms = abs((detected or 0) - 2.0) * 1000
        return {
            "ok": detected is not None and error_ms <= 50,
            "scheduled_seconds": 2.0,
            "detected_seconds": detected,
            "error_ms": error_ms,
            "tolerance_ms": 50,
        }


def verify_continuity(minutes: float) -> dict[str, Any]:
    if minutes <= 0:
        return {"ok": False, "error": "minutes must be positive"}
    duration = minutes * 60
    with tempfile.TemporaryDirectory(prefix="agent-dj-continuity-") as directory:
        output = Path(directory) / "continuity.wav"
        render = run_sc_render("render_continuity.scd", output, duration)
        if not render["ok"]:
            return render
        audio, sample_rate = sf.read(output, always_2d=True, dtype="float32")
        silence_ms = longest_silence(audio, sample_rate)
        peak = float(np.max(np.abs(audio)))
        checks = {
            "duration": len(audio) / sample_rate >= duration - 0.1,
            "finite_samples": bool(np.isfinite(audio).all()),
            "no_unexpected_silence": silence_ms < 100,
            "no_clipping": peak <= 0.891,
            "runtime_crashes": render["returncode"] == 0,
        }
        return {
            "ok": all(checks.values()),
            "requested_minutes": minutes,
            "rendered_seconds": len(audio) / sample_rate,
            "longest_silence_ms": silence_ms,
            "peak_dbfs": dbfs(peak),
            "checks": checks,
        }


def verify_mixer(keep_render: bool = False) -> dict[str, Any]:
    if keep_render:
        session_dir = settings.sessions_dir / "verification" / "renders"
        session_dir.mkdir(parents=True, exist_ok=True)
        output = session_dir / "mixer.wav"
        return render_supercollider_fixture(output)
    with tempfile.TemporaryDirectory(prefix="agent-dj-") as directory:
        return render_supercollider_fixture(Path(directory) / "mixer.wav")
