from pathlib import Path

from dj import config


def test_mrt2_default_prefers_realtime_safe_small_model(
    tmp_path: Path, monkeypatch
) -> None:
    small = tmp_path / "models" / "models" / "mrt2_small" / "mrt2_small.mlxfn"
    base = tmp_path / "models" / "models" / "mrt2_base" / "mrt2_base.mlxfn"
    small.parent.mkdir(parents=True)
    base.parent.mkdir(parents=True)
    small.touch()
    base.touch()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("AGENT_DJ_MRT2_MODEL", raising=False)

    assert config._default_mrt2_model_file() == small


def test_mrt2_environment_override_wins(tmp_path: Path, monkeypatch) -> None:
    chosen = tmp_path / "custom.mlxfn"
    monkeypatch.setenv("AGENT_DJ_MRT2_MODEL", str(chosen))

    assert config._default_mrt2_model_file() == chosen
