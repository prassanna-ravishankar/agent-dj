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
from dj.doctor import inspect_environment
from dj.generator.magenta_live import MagentaLiveGenerator
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckName, DeckStatus
from dj.observations import FeedbackKind, ObservationStore, manual_feedback
from dj.runtime import RuntimeController
from dj.scheduler import ScheduleStore, resolve_bar
from dj.scripted import ScriptedDJ
from dj.session import SessionStore
from dj.transport import Transport
from dj.verification.audio import verify_continuity, verify_mixer, verify_timing
from dj.verification.dual_deck import verify_dual_deck
from dj.verification.feedback import verify_feedback_reaction
from dj.verification.generator import verify_generator
from dj.verification.session import verify_scripted_audio, verify_session

app = typer.Typer(no_args_is_help=True, help="Local-first autonomous DJ control plane.")
verify_app = typer.Typer(no_args_is_help=True, help="Machine-verifiable subsystem checks.")
agent_app = typer.Typer(no_args_is_help=True, help="Local observation-to-music agent.")
app.add_typer(verify_app, name="verify")
app.add_typer(agent_app, name="agent")
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
            table.add_row(str(key), json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value))
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
            audio = verify_scripted_audio(Path(report["render"])) if report.get("render") else {"ok": False}
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
    ObservationStore(
        store.root / state.session_id / "observations.jsonl"
    ).append(observation)
    emit({"ok": True, "observation": observation.model_dump(mode="json"), "event": event}, json_output)


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
    event = store.events().append("parameter_changed", deck=deck, parameter="gain_db", value=gain_db)
    emit({"ok": True, "event": event}, json_output)


@app.command("filter")
def filter_command(
    deck: DeckName,
    kind: str,
    frequency_hz: float,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    SuperColliderMixer().set_filter(deck, kind, frequency_hz)
    event = SessionStore().events().append(
        "parameter_changed", deck=deck, parameter=kind, value=frequency_hz
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
    event = SessionStore().events().append(
        f"recording_{'started' if action == 'start' else 'stopped'}",
        path=str(path) if path else None,
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
        "generation_requested", deck=deck, prompt=conditioned_prompt,
        bpm=bpm, duration_seconds=duration, model="mrt2_small",
    )
    generator = MagentaLiveGenerator()
    output = (
        store.root / state.session_id / "generated" /
        f"{deck.value}-{datetime.now(UTC).strftime('%H%M%S')}.wav"
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
        "generation_ready", deck=deck, path=str(output), model="mrt2_small",
        prompt=conditioned_prompt, requested_event=requested["ts"],
        realtime_factor=health.get("realtime_factor"), local_only=True,
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
