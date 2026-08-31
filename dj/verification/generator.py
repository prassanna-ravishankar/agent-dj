from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.generator.magenta_live import MagentaLiveGenerator
from dj.generator.magenta_offline import MagentaOfflineGenerator
from dj.verification.audio import dbfs, longest_silence, run_sc_render


def _validate_wav(path: Path, requested_duration: float) -> dict[str, Any]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    duration = len(audio) / sample_rate
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak = float(np.max(np.abs(audio)))
    checks = {
        "sample_rate": sample_rate == 48_000,
        "stereo": audio.shape[1] == 2,
        "duration": duration >= requested_duration - 0.05,
        "finite_samples": bool(np.isfinite(audio).all()),
        "non_trivial_rms": rms > 1e-4,
        "no_digital_clipping": peak <= 1.0,
    }
    return {
        "ok": all(checks.values()),
        "sample_rate": sample_rate,
        "channels": audio.shape[1],
        "duration_seconds": duration,
        "rms": rms,
        "peak": peak,
        "checks": checks,
    }


async def _verify(backend: str, duration: float) -> dict[str, Any]:
    generator = (
        MagentaLiveGenerator() if backend == "magenta-live" else MagentaOfflineGenerator()
    )
    prompt = "warm groovy house, percussion-forward, instrumental"
    prepare_started = time.monotonic()
    await generator.prepare(prompt, 124)
    prepare_seconds = time.monotonic() - prepare_started
    await generator.start()
    with tempfile.TemporaryDirectory(prefix="agent-dj-magenta-") as directory:
        root = Path(directory)
        path = root / "generated-a.wav"
        await generator.render(path, duration)
        wav_report = _validate_wav(path, duration)
        live_report: dict[str, Any] | None = None
        if backend == "magenta-live":
            path_b = root / "generated-b.wav"
            await generator.update_conditioning(
                "dark hypnotic rolling house, restrained acid bass, instrumental"
            )
            await generator.render(path_b, duration)
            audio_a, _ = sf.read(path, always_2d=True, dtype="float32")
            audio_b, _ = sf.read(path_b, always_2d=True, dtype="float32")
            common = min(len(audio_a), len(audio_b))
            mean_difference = float(np.mean(np.abs(audio_a[:common] - audio_b[:common])))
            mixed = root / "continuous-transition.wav"
            render = run_sc_render(
                "render_generated_transition.scd",
                mixed,
                max(4.0, duration * 2),
                {
                    "AGENT_DJ_DECK_A": str(path),
                    "AGENT_DJ_DECK_B": str(path_b),
                },
            )
            if render["ok"]:
                mixed_audio, mixed_rate = sf.read(mixed, always_2d=True, dtype="float32")
                silence_ms = longest_silence(mixed_audio, mixed_rate)
                peak = float(np.max(np.abs(mixed_audio)))
                live_checks = {
                    "conditioning_changed_output": mean_difference > 1e-5,
                    "continuous_supercollider_output": silence_ms < 100,
                    "finite_samples": bool(np.isfinite(mixed_audio).all()),
                    "no_clipping": peak <= 0.891,
                }
                live_report = {
                    "ok": all(live_checks.values()),
                    "checks": live_checks,
                    "mean_conditioning_output_difference": mean_difference,
                    "longest_silence_ms": silence_ms,
                    "peak_dbfs": dbfs(peak),
                    "rendered_seconds": len(mixed_audio) / mixed_rate,
                }
            else:
                live_report = render
        health = await generator.health()
    await generator.stop()
    realtime_factor = float(health.get("realtime_factor", 999))
    classification = "streaming" if realtime_factor < 1 else "prebuffered" if realtime_factor < 2 else "offline-only"
    return {
        "ok": wav_report["ok"] and health["ok"] and (live_report or {"ok": True})["ok"],
        "backend": backend,
        "classification": classification,
        "prepare_seconds": prepare_seconds,
        "generation": health,
        "audio": wav_report,
        "live": live_report,
    }


def verify_generator(backend: str, duration: float = 4.0) -> dict[str, Any]:
    if backend not in {"magenta-offline", "magenta-live"}:
        return {"ok": False, "error": f"unsupported backend: {backend}"}
    return asyncio.run(_verify(backend, duration))
