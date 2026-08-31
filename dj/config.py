from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


class Settings(BaseModel):
    project_root: Path = PROJECT_ROOT
    sessions_dir: Path = PROJECT_ROOT / "sessions"
    models_dir: Path = PROJECT_ROOT / "models"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)


settings = Settings()

