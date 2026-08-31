from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.generator.magenta_live import MagentaLiveGenerator
from dj.verification.audio import dbfs, longest_silence, run_sc_render


async def _verify(minutes: float) -> dict[str, Any]:
    generator = MagentaLiveGenerator()
    with tempfile.TemporaryDirectory(prefix="agent-dj-dual-") as directory:
        root = Path(directory)
        deck_a = root / "deck-a.wav"
        deck_b = root / "deck-b.wav"
        await generator.prepare("warm groovy house, percussion-forward, instrumental", 124)
        await generator.start()
        await generator.render(deck_a, 4)
        await generator.update_conditioning(
            "dark hypnotic rolling house, restrained acid bass, instrumental"
        )
        await generator.render(deck_b, 4)
        health = await generator.health()
        await generator.stop()
        output = root / "dual-deck.wav"
        duration = minutes * 60
        render = run_sc_render(
            "render_generated_transition.scd",
            output,
            duration,
            {"AGENT_DJ_DECK_A": str(deck_a), "AGENT_DJ_DECK_B": str(deck_b)},
        )
        if not render["ok"]:
            return render
        audio, sample_rate = sf.read(output, always_2d=True, dtype="float32")
        a, _ = sf.read(deck_a, always_2d=True, dtype="float32")
        b, _ = sf.read(deck_b, always_2d=True, dtype="float32")
        peak = float(np.max(np.abs(audio)))
        silence_ms = longest_silence(audio, sample_rate)
        checks = {
            "independent_generated_material": float(np.mean(np.abs(a - b))) > 1e-5,
            "requested_duration": len(audio) / sample_rate >= duration - 0.1,
            "no_runtime_crash": render["returncode"] == 0,
            "no_audio_starvation": silence_ms < 100,
            "finite_samples": bool(np.isfinite(audio).all()),
            "no_clipping": peak <= 0.891,
            "generation_faster_than_realtime": float(health["realtime_factor"]) < 1,
        }
        return {
            "ok": all(checks.values()),
            "requested_minutes": minutes,
            "rendered_seconds": len(audio) / sample_rate,
            "longest_silence_ms": silence_ms,
            "peak_dbfs": dbfs(peak),
            "generator": health,
            "checks": checks,
        }


def verify_dual_deck(minutes: float) -> dict[str, Any]:
    if minutes <= 0:
        return {"ok": False, "error": "minutes must be positive"}
    return asyncio.run(_verify(minutes))

