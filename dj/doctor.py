from __future__ import annotations

import importlib.util
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from dj.config import settings

SC_APP = Path("/Applications/SuperCollider.app/Contents/MacOS")
SC_RESOURCES = Path("/Applications/SuperCollider.app/Contents/Resources")


def find_executable(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    bundled = SC_APP / name
    if bundled.exists():
        return str(bundled)
    resource = SC_RESOURCES / name
    return str(resource) if resource.exists() else None


def command_version(command: str | None, *args: str) -> str | None:
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, *args], capture_output=True, text=True, timeout=8, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None


def supercollider_version() -> str | None:
    plist = Path("/Applications/SuperCollider.app/Contents/Info.plist")
    if not plist.exists():
        return None
    with plist.open("rb") as stream:
        metadata = plistlib.load(stream)
    return metadata.get("CFBundleShortVersionString")


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def inspect_environment() -> dict[str, Any]:
    sclang = find_executable("sclang")
    scsynth = find_executable("scsynth")
    free = shutil.disk_usage(settings.project_root).free
    magenta_cli = shutil.which("mrt")
    magenta_python = module_available("magenta_rt") or module_available("magentart")
    mrt2_state = settings.mrt2.model_file.with_name(
        f"{settings.mrt2.model_file.stem}_state.safetensors"
    )
    mrt2_extension_files = [
        settings.mrt2.extension_dir / name
        for name in ("MRT2.scx", "MRT2.sc", "mlx.metallib")
    ]
    report: dict[str, Any] = {
        "ok": False,
        "platform": {
            "os": platform.system(),
            "release": platform.mac_ver()[0],
            "arch": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "supported": sys.version_info[:2] == (3, 12),
        },
        "uv": {
            "available": shutil.which("uv") is not None,
            "path": shutil.which("uv"),
        },
        "supercollider": {
            "sclang": sclang,
            "scsynth": scsynth,
            "installed": bool(sclang and scsynth),
            "version": supercollider_version(),
        },
        "magenta": {
            "python": magenta_python,
            "cli": magenta_cli,
            "models_dir": str(settings.models_dir),
            "small_model": any(settings.models_dir.rglob("*mrt2_small*")),
            "live_backend": "mlx" if magenta_python and platform.machine() == "arm64" else None,
        },
        "mrt2_stream": {
            "model": str(settings.mrt2.model_file),
            "model_variant": settings.mrt2.model_file.stem,
            "selection": (
                "environment" if "AGENT_DJ_MRT2_MODEL" in os.environ
                else "realtime_safe_default"
            ),
            "model_ready": settings.mrt2.model_file.exists() and mrt2_state.exists(),
            "assets_ready": (settings.mrt2.assets_dir / "musiccoca" / "spm.model").exists(),
            "extension": str(settings.mrt2.extension_dir),
            "extension_ready": all(path.exists() for path in mrt2_extension_files),
        },
        "essentia": module_available("essentia"),
        "audio": {
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "sample_rate": settings.audio.sample_rate,
        },
        "storage": {
            "sessions_dir": str(settings.sessions_dir),
            "writable": settings.project_root.exists() and settings.project_root.is_dir(),
            "free_bytes": free,
        },
        "local_only": True,
    }
    report["ok"] = all(
        (
            report["platform"]["os"] == "Darwin",
            report["platform"]["arch"] == "arm64",
            report["python"]["supported"],
            report["uv"]["available"],
            report["supercollider"]["installed"],
            report["storage"]["writable"],
        )
    )
    return report
