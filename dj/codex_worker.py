from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any

from dj.config import settings

ALLOWED_METHODS = {
    "model/list",
    "thread/list",
    "thread/read",
    "thread/resume",
    "thread/start",
    "thread/turns/list",
    "turn/interrupt",
    "turn/start",
    "turn/steer",
}
LIFECYCLE_NOTIFICATIONS = {"turn/started", "turn/completed", "error"}


class CodexBridgeWorker:
    def __init__(self, executable: str) -> None:
        self.executable = executable
        self.process: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.next_id = 1
        self.reader_task: asyncio.Task[None] | None = None
        self.server: asyncio.AbstractServer | None = None
        self.stopping = asyncio.Event()
        self.ready_file = settings.sessions_dir / ".codex-bridge-ready"
        self.pid_file = settings.sessions_dir / ".codex-bridge-pid"
        self.socket_file = settings.sessions_dir / ".codex-bridge.sock"
        self.event_file = settings.sessions_dir / ".codex-bridge-events.jsonl"

    async def run(self) -> None:
        settings.sessions_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(settings.sessions_dir, 0o700)
        self.socket_file.unlink(missing_ok=True)
        self.process = await asyncio.create_subprocess_exec(
            self.executable,
            "app-server",
            "--listen",
            "stdio://",
            cwd=settings.project_root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.reader_task = asyncio.create_task(self._read_app_server())
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agent_dj",
                    "title": "Agent DJ",
                    "version": "0.2.0",
                }
            },
        )
        await self._send({"method": "initialized", "params": {}})
        self.server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_file)
        )
        os.chmod(self.socket_file, 0o600)
        self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
        self.ready_file.write_text("ready\n", encoding="utf-8")
        try:
            await self.stopping.wait()
        finally:
            await self.close()

    async def close(self) -> None:
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        self.socket_file.unlink(missing_ok=True)
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader_task is not None:
            self.reader_task.cancel()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            request = json.loads(line)
            method = request["method"]
            if method == "bridge/ping":
                result = {"pong": True}
            elif method not in ALLOWED_METHODS:
                raise ValueError(f"unsupported Codex bridge method: {method}")
            else:
                result = await self._request(method, request.get("params", {}))
            response = {"result": result}
        except Exception as exc:  # noqa: BLE001 - isolate malformed local RPC clients
            response = {"error": str(exc)}
        writer.write((json.dumps(response, separators=(",", ":")) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        await self._send({"method": method, "id": request_id, "params": params})
        try:
            return await asyncio.wait_for(future, 60)
        finally:
            self.pending.pop(request_id, None)

    async def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is not running")
        self.process.stdin.write(
            (json.dumps(message, separators=(",", ":")) + "\n").encode()
        )
        await self.process.stdin.drain()

    async def _read_app_server(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while line := await self.process.stdout.readline():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print(line.decode(errors="replace").rstrip(), flush=True)
                continue
            request_id = message.get("id")
            if "method" in message:
                if request_id is not None:
                    await self._send(
                        {
                            "id": request_id,
                            "error": {
                                "code": -32601,
                                "message": "Agent DJ does not support server-initiated requests",
                            },
                        }
                    )
                else:
                    self._record_notification(message)
                continue
            if request_id not in self.pending:
                continue
            future = self.pending[request_id]
            if "error" in message:
                error = message["error"]
                future.set_exception(RuntimeError(error.get("message", str(error))))
            else:
                result = message.get("result", {})
                future.set_result(result if isinstance(result, dict) else {})
        if not self.stopping.is_set():
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("Codex app-server exited"))
            self.stopping.set()

    def _record_notification(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if method not in LIFECYCLE_NOTIFICATIONS:
            return
        params = message.get("params", {})
        record: dict[str, Any] = {"method": method}
        if isinstance(params, dict):
            record["thread_id"] = params.get("threadId")
            turn = params.get("turn")
            if isinstance(turn, dict):
                record["turn_id"] = turn.get("id")
                record["turn_status"] = turn.get("status")
            error = params.get("error")
            if isinstance(error, dict):
                record["error"] = error.get("message")
        with self.event_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")


async def async_main(executable: str) -> None:
    worker = CodexBridgeWorker(executable)
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, worker.stopping.set)
    await worker.run()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(async_main(str(args.codex)))


if __name__ == "__main__":
    main()
