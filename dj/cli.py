from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from dj.agent import AgentController
from dj.analysis.local import LocalAnalyzer
from dj.codex_client import CodexAppServer
from dj.deck_keeper import DeckKeeper
from dj.doctor import inspect_environment
from dj.generator.magenta_live import MagentaLiveGenerator
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckName, DeckStatus
from dj.observations import FeedbackKind, ObservationStore, manual_feedback
from dj.runtime import RuntimeController
from dj.scheduler import ScheduleStore, resolve_bar
from dj.scripted import ScriptedDJ
from dj.session import SessionStore
from dj.set_conductor import SetConductor
from dj.transport import Transport
from dj.verification.audio import (
    verify_continuity,
    verify_mixer,
    verify_stream_guard,
    verify_timing,
)
from dj.verification.dual_deck import verify_dual_deck
from dj.verification.failures import verify_failure_matrix
from dj.verification.feedback import verify_feedback_reaction
from dj.verification.generator import verify_generator, verify_official_mrt2_stream
from dj.verification.session import verify_scripted_audio, verify_session

app = typer.Typer(no_args_is_help=True, help="Local-first autonomous DJ control plane.")
verify_app = typer.Typer(no_args_is_help=True, help="Machine-verifiable subsystem checks.")
agent_app = typer.Typer(
    no_args_is_help=True,
    help="Triggered local music decisions; the persistent observation worker is optional.",
)
stream_app = typer.Typer(no_args_is_help=True, help="Continuous local MRT2 stream controls.")
codex_app = typer.Typer(no_args_is_help=True, help="Project-local Codex thread controls.")
set_app = typer.Typer(no_args_is_help=True, help="Brief once, then steer a long local set.")
app.add_typer(verify_app, name="verify")
app.add_typer(agent_app, name="agent")
app.add_typer(stream_app, name="stream")
app.add_typer(codex_app, name="codex")
app.add_typer(set_app, name="set")
console = Console()


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"


def emit(data: Any, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    if isinstance(data, dict):
        table = Table(show_header=False, box=None)
        for key, value in data.items():
            table.add_row(
                str(key),
                json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value),
            )
        console.print(table)
    else:
        console.print(data)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Inspect local runtime capabilities without changing the machine."""
    report = inspect_environment()
    emit(report, json_output)
    if not report["ok"]:
        raise typer.Exit(1)


@verify_app.command("environment")
def verify_environment(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Verify the required Milestone 0 environment."""
    report = inspect_environment()
    result = {
        "ok": report["ok"],
        "check": "environment",
        "report": report,
    }
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("mixer")
def verify_mixer_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    keep_render: bool = typer.Option(False, "--keep-render", help="Keep the rendered WAV."),
) -> None:
    """Render the SuperCollider graph and prove mixer operations numerically."""
    result = verify_mixer(keep_render=keep_render)
    result["check"] = "mixer"
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("timing")
def verify_timing_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Prove a scheduled audio change occurs within 50 milliseconds."""
    result = {"check": "timing", **verify_timing()}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("continuity")
def verify_continuity_command(
    minutes: float = typer.Option(2.0, "--minutes", min=0.01),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Keep the real audio server running while the control plane is absent."""
    result = {"check": "continuity", **verify_continuity(minutes)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("stream-guard")
def verify_stream_guard_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    keep_render: bool = typer.Option(False, "--keep-render", help="Keep the rendered WAV."),
) -> None:
    """Prove stream qualification, failure fallback, recovery, and post-master continuity."""
    result = {"check": "stream-guard", **verify_stream_guard(keep_render=keep_render)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("failures")
def verify_failures_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Prove UI, agent, generator, and model failures cannot stop fallback audio."""
    result = {"check": "failures", **verify_failure_matrix()}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("generator")
def verify_generator_command(
    backend: str = typer.Option("magenta-offline", "--backend"),
    duration: float = typer.Option(4.0, "--duration", min=1.0),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Generate and numerically validate real local MRT2 audio."""
    result = {"check": "generator", **verify_generator(backend, duration)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("mrt2-stream")
def verify_mrt2_stream_command(
    duration: float = typer.Option(8.0, "--duration", min=2.0, max=120.0),
    json_output: bool = typer.Option(False, "--json"),
    keep_render: bool = typer.Option(False, "--keep-render"),
) -> None:
    """Render and validate the official continuous MRT2 SuperCollider UGen."""
    result = {
        "check": "mrt2-stream",
        **verify_official_mrt2_stream(duration=duration, keep_render=keep_render),
    }
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("dual-deck")
def verify_dual_deck_command(
    minutes: float = typer.Option(5.0, "--minutes", min=0.05),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    result = {"check": "dual-deck", **verify_dual_deck(minutes)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("feedback")
def verify_feedback_command(
    backend: str = typer.Option("fake", "--backend"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Prove a generic input creates a scheduled, audible local response."""
    result = {"check": "feedback", **verify_feedback_reaction(backend)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("scripted-set")
def verify_scripted_set_command(
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run a deterministic DJ through the same public CLI an external agent uses."""
    store = SessionStore()
    if RuntimeController().status()["running"] or AgentController().status()["running"]:
        result = {"ok": False, "error": "refusing to disturb an active runtime or agent"}
    else:
        previous = store.current_id()
        try:
            performance = ScriptedDJ().perform()
            report = verify_session(performance["session_id"])
            audio = (
                verify_scripted_audio(Path(report["render"]))
                if report.get("render")
                else {"ok": False}
            )
            result = {
                "ok": bool(report["ok"] and audio["ok"]),
                "performance": performance,
                "session": report,
                "audio_sequence": audio,
            }
        finally:
            if previous is None:
                store.current_file.unlink(missing_ok=True)
            else:
                store.current_file.write_text(previous, encoding="utf-8")
    emit({"check": "scripted-set", **result}, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@verify_app.command("session")
def verify_session_command(
    session: str = typer.Argument("latest"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Automatically evaluate a recorded external-agent session."""
    result = {"check": "session", **verify_session(session)}
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@app.command()
def state(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show canonical state for the current session."""
    store = SessionStore()
    current = store.load()
    store.events().append(
        "state_inspected", future_coverage_seconds=current.future.estimated_seconds
    )
    emit(current.model_dump(mode="json"), json_output)


@app.command("events")
def events_command(
    limit: int = typer.Option(20, "--limit", min=1, max=500),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Read recent append-only operational events for the current session."""
    store = SessionStore()
    current = store.load(create=False)
    event_log = store.events(current.session_id)
    recent = event_log.read()[-limit:]
    event_log.append("events_inspected", limit=limit, returned=len(recent))
    emit({"ok": True, "events": recent}, json_output)


@app.command()
def start(
    test_mode: bool = typer.Option(False, "--test-mode"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Start the local SuperCollider runtime."""
    result = RuntimeController().start(test_mode=test_mode)
    emit(result, json_output)


@app.command()
def stop(json_output: bool = typer.Option(False, "--json")) -> None:
    """Stop the local audio runtime cleanly."""
    emit(RuntimeController().stop(), json_output)


@app.command()
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(RuntimeController().status(), json_output)


@app.command("web")
def web_command(
    port: int = typer.Option(8765, "--port", min=1024, max=65535),
    json_output: bool = typer.Option(False, "--json", help="Emit startup JSON."),
) -> None:
    """Serve the local browser control surface on loopback only."""
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if not (dist / "index.html").exists():
        raise typer.BadParameter("web/dist is missing; run `cd web && npm run build`")
    emit(
        {
            "ok": True,
            "url": f"http://127.0.0.1:{port}",
            "local_only": True,
            "audio_path": False,
        },
        json_output,
    )
    uvicorn.run("dj.web_server:app", host="127.0.0.1", port=port, log_level="warning")


@agent_app.command("start")
def agent_start(
    test_mode: bool = typer.Option(False, "--test-mode", help="Use deterministic tones."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Start the entirely local observation and policy worker."""
    emit(AgentController().start(test_mode=test_mode), json_output)


@agent_app.command("stop")
def agent_stop(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(AgentController().stop(), json_output)


@agent_app.command("status")
def agent_status(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(AgentController().status(), json_output)


@agent_app.command("prepare-next")
def agent_prepare_next(
    direction: str | None = typer.Option(
        None, "--direction", help="Optional direction; otherwise derive one from the playing deck."
    ),
    duration: float = typer.Option(64.0, "--duration", min=2.0, max=600.0),
    bpm: float | None = typer.Option(None, "--bpm", min=40.0, max=240.0),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run one local off-air deck preparation job, then exit without starting the agent."""
    result = DeckKeeper().prepare(direction=direction, duration=duration, bpm=bpm)
    emit(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)


@set_app.command("start")
def set_start(
    brief: str = typer.Option(..., "--brief", help="High-level musical direction."),
    minutes: int = typer.Option(90, "--minutes", min=15, max=720),
    test_mode: bool = typer.Option(False, "--test-mode", help="Use deterministic test audio."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Explicitly start audio and an event-driven, token-free local set conductor."""
    emit(SetConductor().start_set(brief, minutes, test_mode=test_mode), json_output)


@set_app.command("status")
def set_status(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(SetConductor().status(), json_output)


@set_app.command("steer")
def set_steer(
    text: str = typer.Option(..., "--text", help="Plain-language direction for the next passage."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    emit(SetConductor().steer(text), json_output)


@set_app.command("hold")
def set_hold(json_output: bool = typer.Option(False, "--json")) -> None:
    """Freeze new conductor decisions without touching audio."""
    emit(SetConductor().hold(True), json_output)


@set_app.command("resume")
def set_resume(json_output: bool = typer.Option(False, "--json")) -> None:
    emit(SetConductor().hold(False), json_output)


@set_app.command("end")
def set_end(json_output: bool = typer.Option(False, "--json")) -> None:
    """End conductor decisions; the current music keeps looping."""
    emit(SetConductor().end(), json_output)


@stream_app.command("status")
def stream_status(json_output: bool = typer.Option(False, "--json")) -> None:
    """Inspect configured intent and live stream/fallback health."""
    store = SessionStore()
    state = store.load()
    live = RuntimeController(store).status()["stream"]
    store.events().append("stream_inspected")
    emit({"ok": True, "configured": state.stream.model_dump(), "live": live}, json_output)


@stream_app.command("start")
def stream_start(json_output: bool = typer.Option(False, "--json")) -> None:
    """Request MRT2 on air; the guard waits for healthy signal before leaving fallback."""
    store = SessionStore()
    state = store.load()
    state.stream.enabled = True
    state.stream.force_fallback = False
    store.save(state)
    runtime = RuntimeController(store).status()
    if runtime["running"]:
        mixer = SuperColliderMixer()
        mixer.stream_force_fallback(False)
        mixer.stream_enable(True)
    event = store.events().append("stream_enabled", guarded=True)
    emit({"ok": True, "event": event, "stream": state.stream.model_dump()}, json_output)


@stream_app.command("stop")
def stream_stop(json_output: bool = typer.Option(False, "--json")) -> None:
    """Return to the looping safety deck without stopping the MRT2 generator."""
    store = SessionStore()
    state = store.load()
    state.stream.enabled = False
    store.save(state)
    if RuntimeController(store).status()["running"]:
        SuperColliderMixer().stream_enable(False)
    event = store.events().append("stream_disabled", fallback_continues=True)
    emit({"ok": True, "event": event, "stream": state.stream.model_dump()}, json_output)


@stream_app.command("prompt")
def stream_prompt(
    slot: int = typer.Argument(..., min=0, max=5),
    text: str = typer.Option(..., "--text"),
    weight: float = typer.Option(1.0, "--weight", min=0, max=1),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Encode a prompt into one of six reusable morph slots."""
    if not text.strip():
        raise typer.BadParameter("prompt text must not be empty")
    store = SessionStore()
    state = store.load()
    prompt = state.stream.prompts[slot]
    prompt.text = text.strip()
    prompt.weight = weight
    store.save(state)
    if RuntimeController(store).status()["running"]:
        SuperColliderMixer().stream_prompt(slot, prompt.text, weight)
    event = store.events().append(
        "stream_prompt_changed", slot=slot, prompt=prompt.text, weight=weight
    )
    emit({"ok": True, "event": event, "prompt": prompt.model_dump()}, json_output)


@stream_app.command("weight")
def stream_weight(
    slot: int = typer.Argument(..., min=0, max=5),
    weight: float = typer.Argument(..., min=0, max=1),
    seconds: float = typer.Option(0.0, "--seconds", min=0, max=600),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Morph a cached prompt weight without re-running the text encoder."""
    store = SessionStore()
    state = store.load()
    prompt = state.stream.prompts[slot]
    if not prompt.text:
        raise typer.BadParameter(f"stream prompt slot {slot} is empty")
    previous = prompt.weight
    prompt.weight = weight
    store.save(state)
    if RuntimeController(store).status()["running"]:
        SuperColliderMixer().stream_weight(slot, weight, seconds)
    event = store.events().append(
        "stream_weight_morphed",
        slot=slot,
        from_weight=previous,
        to_weight=weight,
        duration_seconds=seconds,
    )
    emit({"ok": True, "event": event, "prompt": prompt.model_dump()}, json_output)


@stream_app.command("clear")
def stream_clear(
    slot: int = typer.Argument(..., min=0, max=5),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store = SessionStore()
    state = store.load()
    state.stream.prompts[slot].text = ""
    state.stream.prompts[slot].weight = 0.0
    store.save(state)
    if RuntimeController(store).status()["running"]:
        SuperColliderMixer().stream_clear(slot)
    event = store.events().append("stream_prompt_cleared", slot=slot)
    emit({"ok": True, "event": event}, json_output)


@stream_app.command("fallback")
def stream_fallback(
    enabled: bool = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Force or release the looping safety deck."""
    store = SessionStore()
    state = store.load()
    state.stream.force_fallback = enabled
    store.save(state)
    if RuntimeController(store).status()["running"]:
        SuperColliderMixer().stream_force_fallback(enabled)
    event = store.events().append("stream_fallback_forced", enabled=enabled)
    emit({"ok": True, "event": event}, json_output)


@stream_app.command("settings")
def stream_settings(
    temperature: float = typer.Option(1.0, "--temperature", min=0.1, max=4),
    top_k: int = typer.Option(40, "--top-k", min=1, max=2048),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store = SessionStore()
    state = store.load()
    state.stream.temperature = temperature
    state.stream.top_k = top_k
    store.save(state)
    if RuntimeController(store).status()["running"]:
        mixer = SuperColliderMixer()
        mixer.stream_temperature(temperature)
        mixer.stream_top_k(top_k)
    event = store.events().append("stream_settings_changed", temperature=temperature, top_k=top_k)
    emit({"ok": True, "event": event, "stream": state.stream.model_dump()}, json_output)


@stream_app.command("schedule")
def stream_schedule(
    slot: int = typer.Argument(..., min=0, max=5),
    weight: float = typer.Option(..., "--weight", min=0, max=1),
    at: str = typer.Option("next-16", "--at"),
    bars: float = typer.Option(8, "--bars", min=0.25, max=128),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Schedule a cached prompt to morph at a musical boundary."""
    store = SessionStore()
    state = store.load()
    if not state.stream.prompts[slot].text:
        raise typer.BadParameter(f"stream prompt slot {slot} is empty")
    at_bar = resolve_bar(at, state)
    item = ScheduleStore(store.root / state.session_id / "schedules.jsonl").append(
        "stream-weight", str(slot), at_bar, weight=weight, bars=bars
    )
    store.events().append("stream_morph_scheduled", **item)
    state.future.covered_until_bar = max(state.future.covered_until_bar, at_bar + round(bars))
    store.save(state)
    emit({"ok": True, "schedule": item}, json_output)


@codex_app.command("status")
def codex_status(json_output: bool = typer.Option(False, "--json")) -> None:
    store = SessionStore()
    state = store.load()
    bridge = CodexAppServer().status()
    store.events().append("codex_inspected", bridge_running=bridge["running"])
    emit({"ok": True, "bridge": bridge, "session": state.codex.model_dump()}, json_output)


@codex_app.command("start")
def codex_start(json_output: bool = typer.Option(False, "--json")) -> None:
    store = SessionStore()
    result = CodexAppServer().start()
    event = store.events().append("codex_bridge_started", pid=result.get("pid"))
    emit({"ok": True, "bridge": result, "event": event}, json_output)


@codex_app.command("stop")
def codex_stop(json_output: bool = typer.Option(False, "--json")) -> None:
    """Stop the web-facing Codex bridge without affecting audio."""
    store = SessionStore()
    result = CodexAppServer().stop()
    event = store.events().append("codex_bridge_stopped", audio_unaffected=True)
    emit({"ok": True, "bridge": result, "event": event}, json_output)


@codex_app.command("threads")
def codex_threads(
    limit: int = typer.Option(20, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store = SessionStore()
    result = CodexAppServer().threads(limit)
    store.events().append("codex_threads_listed", returned=len(result.get("data", [])))
    emit({"ok": True, **result}, json_output)


@codex_app.command("models")
def codex_models(json_output: bool = typer.Option(False, "--json")) -> None:
    store = SessionStore()
    result = CodexAppServer().models()
    store.events().append("codex_models_listed", returned=len(result.get("data", [])))
    emit({"ok": True, **result}, json_output)


@codex_app.command("new")
def codex_new(
    prompt: str | None = typer.Option(None, "--prompt"),
    model: str | None = typer.Option(None, "--model"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store = SessionStore()
    client = CodexAppServer()
    started = client.new_thread(model)
    thread = started["thread"]
    thread_id = str(thread["id"])
    turn: dict[str, object] | None = None
    state = store.load()
    state.codex.thread_id = thread_id
    state.codex.turn_id = None
    state.codex.turn_status = "idle"
    if prompt and prompt.strip():
        turn_result = client.turn(thread_id, prompt.strip())
        turn = turn_result["turn"]
        state.codex.turn_id = str(turn["id"])
        state.codex.turn_status = str(turn["status"])
    store.save(state)
    event = store.events().append(
        "codex_thread_started",
        thread_id=thread_id,
        turn_id=state.codex.turn_id,
        prompt_submitted=turn is not None,
    )
    emit({"ok": True, "thread": thread, "turn": turn, "event": event}, json_output)


@codex_app.command("resume")
def codex_resume(
    thread_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store = SessionStore()
    result = CodexAppServer().resume(thread_id)
    state = store.load()
    state.codex.thread_id = thread_id
    state.codex.turn_id = None
    state.codex.turn_status = "idle"
    store.save(state)
    event = store.events().append("codex_thread_resumed", thread_id=thread_id)
    emit({"ok": True, **result, "event": event}, json_output)


@codex_app.command("send")
def codex_send(
    prompt: str = typer.Option(..., "--prompt"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if not prompt.strip():
        raise typer.BadParameter("prompt must not be empty")
    store = SessionStore()
    state = store.load()
    if state.codex.thread_id is None:
        raise typer.BadParameter("no Codex thread is attached; run `dj codex new` first")
    result = CodexAppServer().turn(state.codex.thread_id, prompt.strip())
    turn = result["turn"]
    state.codex.turn_id = str(turn["id"])
    state.codex.turn_status = str(turn["status"])
    store.save(state)
    event = store.events().append(
        "codex_turn_started",
        thread_id=state.codex.thread_id,
        turn_id=state.codex.turn_id,
    )
    emit({"ok": True, "turn": turn, "event": event}, json_output)


@codex_app.command("steer")
def codex_steer(
    prompt: str = typer.Option(..., "--prompt"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Add direction to the currently running Codex turn."""
    if not prompt.strip():
        raise typer.BadParameter("prompt must not be empty")
    store = SessionStore()
    state = store.load()
    if state.codex.thread_id is None or state.codex.turn_id is None:
        raise typer.BadParameter("no active Codex turn is attached")
    result = CodexAppServer().steer(state.codex.thread_id, state.codex.turn_id, prompt.strip())
    event = store.events().append(
        "codex_turn_steered",
        thread_id=state.codex.thread_id,
        turn_id=state.codex.turn_id,
    )
    emit({"ok": True, **result, "event": event}, json_output)


@codex_app.command("inspect")
def codex_inspect(json_output: bool = typer.Option(False, "--json")) -> None:
    store = SessionStore()
    state = store.load()
    if state.codex.thread_id is None:
        raise typer.BadParameter("no Codex thread is attached")
    result = CodexAppServer().read(state.codex.thread_id)
    thread = result.get("thread", {})
    turns = thread.get("turns", []) if isinstance(thread, dict) else []
    if turns:
        latest = turns[-1]
        state.codex.turn_id = latest.get("id")
        state.codex.turn_status = str(latest.get("status", "unknown"))
        store.save(state)
    store.events().append("codex_thread_inspected", thread_id=state.codex.thread_id)
    emit({"ok": True, **result}, json_output)


@codex_app.command("interrupt")
def codex_interrupt(json_output: bool = typer.Option(False, "--json")) -> None:
    store = SessionStore()
    state = store.load()
    if state.codex.thread_id is None or state.codex.turn_id is None:
        raise typer.BadParameter("no active Codex turn is attached")
    result = CodexAppServer().interrupt(state.codex.thread_id, state.codex.turn_id)
    state.codex.turn_status = "interrupted"
    store.save(state)
    event = store.events().append(
        "codex_turn_interrupted",
        thread_id=state.codex.thread_id,
        turn_id=state.codex.turn_id,
    )
    emit({"ok": True, **result, "event": event}, json_output)


@app.command()
def feedback(
    kind: FeedbackKind,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Submit human feedback through the source-neutral observation boundary."""
    store = SessionStore()
    state = store.load()
    observation = manual_feedback(kind)
    event = store.events().append(
        "observation_received",
        observation_id=observation.id,
        observation=observation.model_dump(mode="json"),
    )
    ObservationStore(store.root / state.session_id / "observations.jsonl").append(observation)
    emit(
        {"ok": True, "observation": observation.model_dump(mode="json"), "event": event},
        json_output,
    )


@app.command(context_settings={"ignore_unknown_options": True})
def gain(
    deck: DeckName,
    gain_db: float,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    mixer = SuperColliderMixer()
    mixer.set_gain(deck, gain_db)
    store = SessionStore()
    state = store.load()
    state.decks[deck].gain_db = gain_db
    store.save(state)
    event = store.events().append(
        "parameter_changed", deck=deck, parameter="gain_db", value=gain_db
    )
    emit({"ok": True, "event": event}, json_output)


@app.command("filter")
def filter_command(
    deck: DeckName,
    kind: str,
    frequency_hz: float,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    SuperColliderMixer().set_filter(deck, kind, frequency_hz)
    event = (
        SessionStore()
        .events()
        .append("parameter_changed", deck=deck, parameter=kind, value=frequency_hz)
    )
    emit({"ok": True, "event": event}, json_output)


@app.command()
def crossfade(
    from_or_target: DeckName,
    target: Annotated[DeckName | None, typer.Argument()] = None,
    bars: float = typer.Option(16, "--bars", min=0),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Crossfade to a deck; accepts either `B` or explicit `A B` form."""
    resolved_target = target or from_or_target
    if target is not None and from_or_target is target:
        raise typer.BadParameter("source and target decks must differ")
    store = SessionStore()
    state = store.load()
    duration = Transport(state.transport.bpm).bars_to_seconds(bars)
    SuperColliderMixer().crossfade(resolved_target, duration)
    for name, deck in state.decks.items():
        deck.status = DeckStatus.PLAYING if name is resolved_target else DeckStatus.PREPARED
    store.save(state)
    event = store.events().append(
        "transition_started",
        from_deck=from_or_target if target is not None else None,
        to=resolved_target,
        duration_bars=bars,
        duration_seconds=duration,
    )
    emit({"ok": True, "event": event}, json_output)


@app.command()
def play(
    deck: DeckName,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Bring a prepared deck on air with a short safe fade."""
    store = SessionStore()
    state = store.load()
    if not state.decks[deck].audio_path:
        raise typer.BadParameter(f"deck {deck.value} has no prepared audio")
    SuperColliderMixer().crossfade(deck, 0.25)
    for name, current in state.decks.items():
        current.status = DeckStatus.PLAYING if name == deck else DeckStatus.PREPARED
    store.save(state)
    event = store.events().append("deck_started", deck=deck)
    emit({"ok": True, "event": event}, json_output)


@app.command("deck-load")
def deck_load(
    deck: DeckName,
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Load a local stereo WAV into a looping deck."""
    SuperColliderMixer().load(deck, path)
    store = SessionStore()
    state = store.load()
    state.decks[deck].audio_path = str(path.resolve())
    already_playing = state.decks[deck].status is DeckStatus.PLAYING
    state.decks[deck].status = DeckStatus.PLAYING if already_playing else DeckStatus.PREPARED
    store.save(state)
    event = store.events().append("deck_prepared", deck=deck, path=str(path.resolve()))
    emit({"ok": True, "event": event}, json_output)


@app.command()
def record(
    action: str,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Start or stop master-bus recording."""
    if action == "start" and path is None:
        state = SessionStore().load()
        path = SessionStore().root / state.session_id / "renders" / "master.wav"
    SuperColliderMixer().record(action, path)
    event = (
        SessionStore()
        .events()
        .append(
            f"recording_{'started' if action == 'start' else 'stopped'}",
            path=str(path) if path else None,
        )
    )
    emit({"ok": True, "event": event}, json_output)


@app.command()
def generate(
    deck: DeckName,
    prompt: str = typer.Option(..., "--prompt"),
    bpm: float = typer.Option(124.0, "--bpm", min=40, max=240),
    duration: float = typer.Option(16.0, "--duration", min=2.0),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Generate a local MRT2 segment and prepare it on a deck."""
    store = SessionStore()
    state = store.load()
    event_log = store.events()
    conditioned_prompt = f"{prompt}, around {bpm:g} BPM"
    requested = event_log.append(
        "generation_requested",
        deck=deck,
        prompt=conditioned_prompt,
        bpm=bpm,
        duration_seconds=duration,
        model="mrt2_small",
    )
    generator = MagentaLiveGenerator()
    output = (
        store.root
        / state.session_id
        / "generated"
        / f"{deck.value}-{datetime.now(UTC).strftime('%H%M%S')}.wav"
    )

    async def run_generation() -> dict[str, Any]:
        try:
            event_log.append("generation_started", deck=deck)
            await generator.prepare(conditioned_prompt, bpm)
            await generator.start()
            await generator.render(output, duration)
            health = await generator.health()
            await generator.stop()
            return health
        except Exception as exc:
            event_log.append("generation_failed", deck=deck, error=str(exc))
            raise

    health = asyncio.run(run_generation())
    state.decks[deck].source = "magenta"
    state.decks[deck].prompt = conditioned_prompt
    state.decks[deck].audio_path = str(output)
    state.decks[deck].duration_seconds = duration
    state.decks[deck].status = DeckStatus.PREPARED
    state.decks[deck].energy = None
    state.future.estimated_seconds = max(state.future.estimated_seconds, duration)
    store.save(state)
    if RuntimeController().status()["running"]:
        SuperColliderMixer().load(deck, output)
    ready = event_log.append(
        "generation_ready",
        deck=deck,
        path=str(output),
        model="mrt2_small",
        prompt=conditioned_prompt,
        requested_event=requested["ts"],
        realtime_factor=health.get("realtime_factor"),
        local_only=True,
    )
    emit({"ok": True, "event": ready, "generator": health}, json_output)


@app.command()
def analyse(
    target: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Analyse a prepared deck or the current master recording locally."""
    store = SessionStore()
    state = store.load()
    if target.upper() in {"A", "B"}:
        path_value = state.decks[DeckName(target.upper())].audio_path
    elif target == "master":
        path_value = str(store.root / state.session_id / "renders" / "master.wav")
    else:
        raise typer.BadParameter("target must be A, B, or master")
    if not path_value or not Path(path_value).exists():
        raise typer.BadParameter(f"no audio available for {target}")
    result = LocalAnalyzer().analyse(Path(path_value))
    store.events().append("analysis_completed", target=target, result=result)
    emit(result, json_output)


@app.command()
def schedule(
    action: str,
    target: str,
    at: str = typer.Option("next-16", "--at"),
    bars: float = typer.Option(16, "--bars", min=0),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Schedule an agent action on the musical clock."""
    store = SessionStore()
    state = store.load()
    at_bar = resolve_bar(at, state)
    schedules = ScheduleStore(store.root / state.session_id / "schedules.jsonl")
    item = schedules.append(action, target, at_bar, bars=bars)
    store.events().append("transition_scheduled", **item)
    state.future.covered_until_bar = max(state.future.covered_until_bar, at_bar + round(bars))
    state.future.estimated_seconds = max(
        state.future.estimated_seconds,
        Transport(state.transport.bpm).bars_to_seconds(max(0, at_bar - state.transport.bar + bars)),
    )
    store.save(state)
    emit({"ok": True, "schedule": item}, json_output)


@app.command("session-new")
def session_new(
    session_id: str | None = typer.Option(None, "--id"),
    duration_minutes: float | None = typer.Option(None, "--duration-minutes", min=0.01),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if RuntimeController().status()["running"] or AgentController().status()["running"]:
        raise typer.BadParameter("stop the active runtime and agent before changing sessions")
    store = SessionStore()
    current = store.create(session_id)
    if duration_minutes is not None:
        store.events().append(
            "set_intent",
            planned_duration_minutes=duration_minutes,
            planned_duration_seconds=duration_minutes * 60,
        )
    emit(current.model_dump(mode="json"), json_output)


if __name__ == "__main__":
    app()
