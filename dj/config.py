from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _default_mrt2_model_file() -> Path:
    configured = os.environ.get("AGENT_DJ_MRT2_MODEL")
    if configured:
        return Path(configured).expanduser()
    # The streaming engine must produce each 40 ms frame in under 40 ms. On the
    # supported M1 Pro development machine, mrt2_base averages ~57 ms/frame while
    # mrt2_small averages ~23 ms/frame. Prefer continuity; base remains an explicit
    # AGENT_DJ_MRT2_MODEL opt-in for faster hardware and offline rendering.
    small = PROJECT_ROOT / "models" / "models" / "mrt2_small" / "mrt2_small.mlxfn"
    if small.exists():
        return small
    return PROJECT_ROOT / "models" / "models" / "mrt2_base" / "mrt2_base.mlxfn"


class CoverageConfig(BaseModel):
    normal_seconds: float = 90.0
    warning_seconds: float = 60.0
    critical_seconds: float = 30.0


class AudioConfig(BaseModel):
    sample_rate: int = 48_000
    channels: int = 2
    limiter_ceiling_dbfs: float = -1.0
    osc_host: str = "127.0.0.1"
    osc_port: int = 57_120


class MRT2Config(BaseModel):
    assets_dir: Path = PROJECT_ROOT / "models" / "resources"
    model_file: Path = Field(default_factory=_default_mrt2_model_file)
    extension_dir: Path = (
        Path.home()
        / "Library"
        / "Application Support"
        / "SuperCollider"
        / "Extensions"
        / "MRT2"
    )
    buffer_samples: int = 8192
    signal_threshold: float = 0.00003


class Settings(BaseModel):
    project_root: Path = PROJECT_ROOT
    sessions_dir: Path = PROJECT_ROOT / "sessions"
    models_dir: Path = PROJECT_ROOT / "models"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    mrt2: MRT2Config = Field(default_factory=MRT2Config)
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)


settings = Settings()
