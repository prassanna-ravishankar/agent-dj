import asyncio
from pathlib import Path

import numpy as np
import soundfile as sf

from dj.generator.fake import FakeGenerator


def test_fake_generator_renders_stereo_fixture(tmp_path: Path) -> None:
    path = asyncio.run(FakeGenerator(440).render(tmp_path / "tone.wav", 0.1))
    audio, sample_rate = sf.read(path, always_2d=True)
    assert sample_rate == 48_000
    assert audio.shape == (4_800, 2)
    assert np.isfinite(audio).all()
    assert np.sqrt(np.mean(np.square(audio))) > 0.1

