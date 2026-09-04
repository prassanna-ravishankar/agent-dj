from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from typing import Any

from dj.config import settings


class CodexError(RuntimeError):
    pass


class CodexAppServer:
    """Client for Agent DJ's project-local Codex app-server bridge."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("codex")
        self.ready_file = settings.sessions_dir / ".codex-bridge-ready"
        self.pid_file = settings.sessions_dir / ".codex-bridge-pid"
        self.socket_file = settings.sessions_dir / ".codex-bridge.sock"

    def status(self) -> dict[str, Any]:
        pid = self._pid()
        candidate = bool(
            pid and self._alive(pid) and self.ready_file.exists() and self.socket_file.exists()
        )
        running = False
        if candidate:
            try:
                running = self._bridge_request("bridge/ping", {}, timeout=0.5).get("pong") is True
            except CodexError:
                running = False
        return {
            "ok": running,
            "running": running,
            "available": self.executable is not None,
            "pid": pid,
            "transport_local_only": True,
            "inference_may_require_network": True,
        }

    def start(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.executable is None:
            raise CodexError("codex executable is not installed")
        if self.status()["running"]:
            return self.status()
        settings.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        self.socket_file.unlink(missing_ok=True)
        log = (settings.sessions_dir / "codex-bridge.log").open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "dj.codex_worker", "--codex", self.executable],
                cwd=settings.project_root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log.close()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.status()["running"]:
                return self.status()
            if process.poll() is not None:
                raise CodexError(f"Codex bridge exited; inspect {log.name}")
            time.sleep(0.1)
        process.terminate()
        raise CodexError(f"Codex bridge did not become ready; inspect {log.name}")

    def stop(self, timeout: float = 8.0) -> dict[str, Any]:
        pid = self._pid()
        if pid is None or not self._alive(pid):
            self.ready_file.unlink(missing_ok=True)
            self.pid_file.unlink(missing_ok=True)
            self.socket_file.unlink(missing_ok=True)
            return {"ok": True, "running": False, "transport_local_only": True}
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self._alive(pid):
            time.sleep(0.05)
        if self._alive(pid):
            raise CodexError("Codex bridge did not stop cleanly")
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        self.socket_file.unlink(missing_ok=True)
        return {"ok": True, "running": False, "transport_local_only": True}

    def models(self) -> dict[str, Any]:
        return self._rpc("model/list", {"limit": 20, "includeHidden": False})

    def threads(self, limit: int = 20) -> dict[str, Any]:
        return self._rpc(
            "thread/list",
            {
                "limit": limit,
                "sortKey": "recency_at",
                "sortDirection": "desc",
                "cwd": str(settings.project_root),
                "sourceKinds": [
                    "appServer",
                    "cli",
                    "vscode",
                    "exec",
                    "subAgent",
                    "subAgentReview",
                    "subAgentCompact",
                    "subAgentThreadSpawn",
                    "subAgentOther",
                ],
            },
        )

    def new_thread(self, model: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(settings.project_root),
            "approvalPolicy": "never",
            "sandbox": "workspace-write",
            "personality": "friendly",
            "serviceName": "agent_dj_web",
        }
        if model:
            params["model"] = model
        return self._rpc("thread/start", params)

    def resume(self, thread_id: str) -> dict[str, Any]:
        return self._rpc("thread/resume", {"threadId": thread_id, "excludeTurns": True})

    def read(self, thread_id: str, limit: int = 20) -> dict[str, Any]:
        metadata = self._rpc("thread/read", {"threadId": thread_id, "includeTurns": False})
        page = self._rpc(
            "thread/turns/list",
            {
                "threadId": thread_id,
                "limit": limit,
                "sortDirection": "desc",
                "itemsView": "full",
            },
        )
        thread = metadata.get("thread", {})
        if isinstance(thread, dict):
            thread["turns"] = list(reversed(page.get("data", [])))
        return {
            "thread": thread,
            "nextCursor": page.get("nextCursor"),
            "backwardsCursor": page.get("backwardsCursor"),
        }

    def turn(self, thread_id: str, prompt: str) -> dict[str, Any]:
        return self._rpc(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(settings.project_root),
                "approvalPolicy": "never",
                "sandboxPolicy": {
                    "type": "workspaceWrite",
                    "writableRoots": [str(settings.project_root)],
                    "networkAccess": False,
                },
                "summary": "concise",
                "personality": "friendly",
                "clientUserMessageId": str(uuid.uuid4()),
            },
        )

    def steer(self, thread_id: str, turn_id: str, prompt: str) -> dict[str, Any]:
        return self._rpc(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": turn_id,
                "input": [{"type": "text", "text": prompt}],
                "clientUserMessageId": str(uuid.uuid4()),
            },
        )

    def interrupt(self, thread_id: str, turn_id: str) -> dict[str, Any]:
        return self._rpc(
            "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}
        )

    def _rpc(
        self, method: str, params: dict[str, Any], timeout: float = 30.0
    ) -> dict[str, Any]:
        if not self.status()["running"]:
            self.start()
        return self._bridge_request(method, params, timeout)

    def _bridge_request(
        self, method: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        request = json.dumps({"method": method, "params": params}, separators=(",", ":"))
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(timeout)
                connection.connect(str(self.socket_file))
                connection.sendall((request + "\n").encode())
                chunks: list[bytes] = []
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if b"\n" in chunk:
                        break
        except OSError as exc:
            raise CodexError(f"Codex bridge is unavailable: {exc}") from exc
        try:
            response = json.loads(b"".join(chunks).splitlines()[0])
        except (IndexError, json.JSONDecodeError) as exc:
            raise CodexError("Codex bridge returned an invalid response") from exc
        if "error" in response:
            raise CodexError(str(response["error"]))
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise CodexError("Codex app-server returned a non-object result")
        return result

    def _pid(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
