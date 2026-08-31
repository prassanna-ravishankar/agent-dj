from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.analysis.base import Analyzer


class LocalAnalyzer(Analyzer):
    """Small local fallback adapter used until optional Essentia is available."""

    def analyse(self, path: Path) -> dict[str, Any]:
        audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
        if len(audio) == 0:
            return {
                "ok": False,
                "path": str(path),
                "error": "audio file contains no frames",
                "sample_rate": sample_rate,
                "channels": audio.shape[1],
            }
        mono = audio.mean(axis=1)
        rms = float(np.sqrt(np.mean(np.square(mono))))
        peak = float(np.max(np.abs(audio)))
        sample = mono[: min(len(mono), sample_rate * 30)]
        spectrum = np.abs(np.fft.rfft(sample * np.hanning(len(sample))))
        frequencies = np.fft.rfftfreq(len(sample), 1 / sample_rate)
        centroid = float(np.sum(frequencies * spectrum) / max(np.sum(spectrum), 1e-12))
        block = 1024
        energies = np.array(
            [np.sqrt(np.mean(np.square(mono[index : index + block]))) for index in range(0, len(mono), block)]
        )
        positive_flux = np.maximum(np.diff(energies), 0)
        threshold = float(np.mean(positive_flux) + 2 * np.std(positive_flux))
        onsets = int(np.count_nonzero(positive_flux > threshold))
        duration = len(audio) / sample_rate
        return {
            "ok": bool(np.isfinite(audio).all()),
            "path": str(path),
            "sample_rate": sample_rate,
            "channels": audio.shape[1],
            "duration_seconds": duration,
            "rms": rms,
            "peak_dbfs": 20 * math.log10(max(peak, 1e-12)),
            "onset_rate": onsets / max(duration, 1e-9),
            "spectral_centroid": centroid,
            "backend": "local-numpy",
        }
