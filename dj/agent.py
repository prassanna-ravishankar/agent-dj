from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any

from dj.config import settings


class AgentController:
    def __init__(self) -> None:
        self.ready_file = settings.sessions_dir / ".agent-ready"
        self.pid_file = settings.sessions_dir / ".agent-pid"

    def status(self) -> dict[str, Any]:
        pid = self._pid()
        running = bool(pid and self._alive(pid) and self.ready_file.exists())
        return {"ok": running, "running": running, "pid": pid, "local_only": True}

    def start(self, test_mode: bool = False, timeout: float = 10.0) -> dict[str, Any]:
        if self.status()["running"]:
            return self.status()
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        args = [sys.executable, "-m", "dj.agent_worker"]
        if test_mode:
            args.append("--test-mode")
        log = (settings.sessions_dir / "agent.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            args, cwd=settings.project_root, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready_file.exists():
                return self.status()
            if process.poll() is not None:
                raise RuntimeError(f"DJ agent exited; inspect {log.name}")
            time.sleep(0.1)
        process.terminate()
        raise TimeoutError(f"DJ agent did not become ready; inspect {log.name}")

    def stop(self, timeout: float = 8.0) -> dict[str, Any]:
        pid = self._pid()
        if pid and self._alive(pid):
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + timeout
            while (
                time.monotonic() < deadline
                and self._alive(pid)
                and self.ready_file.exists()
            ):
                time.sleep(0.1)
            if self._alive(pid) and self.ready_file.exists():
                os.kill(pid, signal.SIGKILL)
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        return {"ok": True, "running": False}

    def _pid(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text().strip())
        except ValueError:
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
