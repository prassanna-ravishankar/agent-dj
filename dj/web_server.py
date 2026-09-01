from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dj.agent import AgentController
from dj.config import settings
from dj.doctor import inspect_environment
from dj.models import DeckName
from dj.observations import FeedbackKind
from dj.runtime import RuntimeController
from dj.session import SessionStore


def _read_jsonl(path: Path, *, inner: str | None = None) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        candidate = value.get(inner, value) if inner else value
        if isinstance(candidate, dict):
            records.append(candidate)
    return records


def _load_state() -> tuple[SessionStore, object]:
    store = SessionStore()
    error: Exception | None = None
    for _ in range(3):
        try:
            return store, store.load(create=False)
        except (OSError, ValueError) as exc:
            error = exc
    raise HTTPException(status_code=409, detail=f"state is temporarily unavailable: {error}")


def _snapshot() -> dict[str, object]:
    store, state = _load_state()
    session_dir = store.root / state.session_id
    return {
        "state": state.model_dump(mode="json"),
        "runtime": RuntimeController(store).status(),
        "agent": AgentController().status(),
        "events": _read_jsonl(session_dir / "events.jsonl"),
        "decisions": _read_jsonl(session_dir / "decisions.jsonl", inner="decision"),
        "schedules": _read_jsonl(session_dir / "schedules.jsonl"),
        "demo": False,
    }


async def _run_dj(*args: str, timeout: float = 30.0) -> dict[str, object]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "dj.cli",
        *args,
        "--json",
        cwd=settings.project_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise HTTPException(status_code=504, detail="local command timed out") from exc
    output = stdout.decode(errors="replace").strip()
    error = stderr.decode(errors="replace").strip()
    if process.returncode != 0:
        detail = error.splitlines()[-1] if error else output or "command refused"
        raise HTTPException(status_code=409, detail=detail)
    if not output:
        return {"ok": True}
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="local command returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=502, detail="local command returned an invalid payload")
    return value


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        store = SessionStore()
        if store.current_id():
            store.events().append("web_server_started", local_only=True)
    except OSError:
        pass
    yield
    try:
        store = SessionStore()
        if store.current_id():
            store.events().append("web_server_stopped", audio_unaffected=True)
    except OSError:
        pass


app = FastAPI(title="Agent DJ local control surface", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(_, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


class TestModeRequest(BaseModel):
    test_mode: bool = False


class GenerateRequest(BaseModel):
    deck: DeckName
    prompt: str = Field(min_length=1, max_length=1000)
    bpm: float = Field(ge=40, le=240)
    duration: float = Field(ge=2, le=600)


class PlayRequest(BaseModel):
    deck: DeckName


class CrossfadeRequest(BaseModel):
    target: DeckName
    bars: float = Field(ge=0, le=256)


class GainRequest(BaseModel):
    deck: DeckName
    gain_db: float = Field(ge=-60, le=12)


class FilterRequest(BaseModel):
    deck: DeckName
    kind: Literal["lowpass", "highpass"]
    frequency_hz: float = Field(gt=0, le=24_000)


class RecordRequest(BaseModel):
    action: Literal["start", "stop"]


class FeedbackRequest(BaseModel):
    kind: FeedbackKind


@app.get("/api/snapshot")
async def snapshot() -> dict[str, object]:
    return _snapshot()


@app.get("/api/doctor")
async def doctor() -> dict[str, object]:
    return inspect_environment()


@app.post("/api/runtime/start")
async def runtime_start(request: TestModeRequest) -> dict[str, object]:
    args = ["start"]
    if request.test_mode:
        args.append("--test-mode")
    return await _run_dj(*args)


@app.post("/api/runtime/stop")
async def runtime_stop() -> dict[str, object]:
    await _run_dj("stop")
    return RuntimeController().status()


@app.post("/api/agent/start")
async def agent_start(request: TestModeRequest) -> dict[str, object]:
    args = ["agent", "start"]
    if request.test_mode:
        args.append("--test-mode")
    return await _run_dj(*args)


@app.post("/api/agent/stop")
async def agent_stop() -> dict[str, object]:
    await _run_dj("agent", "stop")
    return AgentController().status()


async def _no_content(*args: str, timeout: float = 30.0) -> Response:
    await _run_dj(*args, timeout=timeout)
    return Response(status_code=204)


@app.post("/api/generate", status_code=204)
async def generate(request: GenerateRequest) -> Response:
    return await _no_content(
        "generate", request.deck.value, "--prompt", request.prompt, "--bpm", str(request.bpm),
        "--duration", str(request.duration), timeout=600,
    )


@app.post("/api/play", status_code=204)
async def play(request: PlayRequest) -> Response:
    return await _no_content("play", request.deck.value)


@app.post("/api/crossfade", status_code=204)
async def crossfade(request: CrossfadeRequest) -> Response:
    return await _no_content("crossfade", request.target.value, "--bars", str(request.bars))


@app.post("/api/gain", status_code=204)
async def gain(request: GainRequest) -> Response:
    return await _no_content("gain", request.deck.value, str(request.gain_db))


@app.post("/api/filter", status_code=204)
async def filter_command(request: FilterRequest) -> Response:
    return await _no_content(
        "filter", request.deck.value, request.kind, str(request.frequency_hz)
    )


@app.post("/api/record", status_code=204)
async def record(request: RecordRequest) -> Response:
    return await _no_content("record", request.action)


@app.post("/api/feedback", status_code=204)
async def feedback(request: FeedbackRequest) -> Response:
    return await _no_content("feedback", request.kind.value)


def _change_signature() -> tuple[tuple[str, int, int], ...]:
    store = SessionStore()
    current = store.current_id()
    paths = [store.current_file]
    if current:
        root = store.root / current
        paths.extend(root / name for name in (
            "state.json", "events.jsonl", "decisions.jsonl", "schedules.jsonl"
        ))
    signature = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), 0, 0))
    return tuple(signature)


@app.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        previous = _change_signature()
        heartbeat = 0
        while True:
            await asyncio.sleep(0.5)
            if await request.is_disconnected():
                break
            current = _change_signature()
            if current != previous:
                previous = current
                heartbeat = 0
                yield "data: changed\n\n"
            else:
                heartbeat += 1
                if heartbeat >= 30:
                    heartbeat = 0
                    yield ": keepalive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


dist = settings.project_root / "web" / "dist"
if (dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
