from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

from dj.config import settings
from dj.session import SessionStore


class ScriptedDJ:
    """Deterministic agent that operates only through the public CLI."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def command(self, *arguments: str) -> dict[str, Any]:
        argv = [sys.executable, "-m", "dj.cli", *arguments, "--json"]
        result = subprocess.run(
            argv,
            cwd=settings.project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.commands.append(list(arguments))
        if result.returncode != 0:
            raise RuntimeError(
                f"public command failed ({' '.join(arguments)}): "
                f"{result.stderr or result.stdout}"
            )
        return json.loads(result.stdout)

    def perform(self) -> dict[str, Any]:
        session_id = f"scripted-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        self.command("session-new", "--id", session_id)
        store = SessionStore()
        store.events().append("scripted_set_started", planned_duration_seconds=3.5)
        try:
            self.command("start", "--test-mode")
            self.command("agent", "start", "--test-mode")
            self.command("record", "start")
            time.sleep(0.5)
            self.command("state")
            self.command("gain", "A", "0")
            self.command("filter", "A", "lowpass", "10000")
            self.command("schedule", "crossfade", "B", "--at", "bar+0", "--bars", "0.1")
            time.sleep(1.5)
            self.command("state")
            self.command("schedule", "crossfade", "A", "--at", "bar+0", "--bars", "0.1")
            time.sleep(1.5)
            self.command("record", "stop")
            time.sleep(0.4)
            self.command("analyse", "master")
            store.events().append("scripted_set_completed", session_id=session_id)
            return {"session_id": session_id, "commands": self.commands}
        finally:
            try:
                self.command("agent", "stop")
            finally:
                self.command("stop")
