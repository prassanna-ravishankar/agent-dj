from __future__ import annotations

import json
import subprocess
import sys
from typing import Literal

from mcp.server import MCPServer

from dj.config import settings

INSTRUCTIONS = """Music must not stop. Call dj_inspect before every musical action and verify
future coverage first. Extend unsafe coverage before creative changes. Use only these certified
tools during a live session; never improvise shell commands, edit code, install dependencies,
restart the runtime, or delete audio. The browser, MCP server, agent, and analyser are disposable:
their failure must never interrupt the playing deck. Prefer continuing a safe deck to an
unnecessary change. Schedule transitions in bars, not wall-clock seconds. Record concise musical
intent and evidence, never private reasoning traces."""

mcp = MCPServer("Agent DJ", version="0.1.0", instructions=INSTRUCTIONS)


class DJCommandError(RuntimeError):
    pass


def _command(*arguments: str, timeout: float = 30.0) -> dict[str, object]:
    """Run one certified public CLI command and return its JSON payload."""
    result = subprocess.run(
        [sys.executable, "-m", "dj.cli", *arguments, "--json"],
        cwd=settings.project_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command refused").strip()
        raise DJCommandError(f"certified command failed ({' '.join(arguments)}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DJCommandError("certified command returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DJCommandError("certified command returned a non-object payload")
    return payload


def _coverage_state(seconds: float) -> str:
    if seconds >= 90:
        return "safe"
    if seconds < 30:
        return "critical"
    if seconds < 60:
        return "warning"
    return "caution"


def _combined_state() -> dict[str, object]:
    state = _command("state")
    runtime = _command("status")
    agent = _command("agent", "status")
    future = state["future"]
    assert isinstance(future, dict)
    seconds = float(future["estimated_seconds"])
    decks = state["decks"]
    assert isinstance(decks, dict)
    on_air = next(
        (
            name
            for name, value in decks.items()
            if isinstance(value, dict) and value.get("status") == "playing"
        ),
        None,
    )
    return {
        "state": state,
        "runtime": runtime,
        "agent": agent,
        "safety": {
            "coverage": _coverage_state(seconds),
            "future_seconds": seconds,
            "safe_loop": seconds >= 86_400,
            "on_air_deck": on_air,
            "music_must_not_stop": True,
        },
    }


def _target_deck(snapshot: dict[str, object], requested: Literal["A", "B"] | None) -> str:
    state = snapshot["state"]
    assert isinstance(state, dict)
    decks = state["decks"]
    assert isinstance(decks, dict)
    if requested:
        return requested
    on_air = next(
        (
            name
            for name, value in decks.items()
            if isinstance(value, dict) and value.get("status") == "playing"
        ),
        "A",
    )
    return "B" if on_air == "A" else "A"


def _require_safe_creative_change(snapshot: dict[str, object]) -> None:
    state = snapshot["state"]
    safety = snapshot["safety"]
    runtime = snapshot["runtime"]
    assert isinstance(state, dict) and isinstance(safety, dict) and isinstance(runtime, dict)
    if safety["coverage"] != "critical":
        return
    # With audio stopped, preparation is how an empty session becomes safe. During a live set,
    # however, creative work cannot take precedence over establishing a playing buffer.
    if not runtime.get("running"):
        return
    decks = state["decks"]
    assert isinstance(decks, dict)
    has_playing_audio = any(
        isinstance(deck, dict)
        and deck.get("status") == "playing"
        and bool(deck.get("audio_path"))
        for deck in decks.values()
    )
    if not has_playing_audio:
        raise DJCommandError(
            "creative change refused: future coverage is critical and no safe playing buffer exists"
        )


@mcp.tool()
def dj_inspect() -> dict[str, object]:
    """Inspect canonical DJ state, runtime/agent health, and future-coverage safety."""
    return _combined_state()


@mcp.tool()
def dj_submit_observation(
    kind: Literal["love", "dislike", "more-energy", "less-energy", "boring", "weird"],
) -> dict[str, object]:
    """Record a source-neutral musical observation for the local policy worker."""
    snapshot = _combined_state()
    result = _command("feedback", kind)
    agent = snapshot["agent"]
    assert isinstance(agent, dict)
    return {
        "accepted": True,
        "observation": result,
        "agent_running": bool(agent.get("running")),
        "consequence": (
            "the local agent will prepare a phrase-aligned response"
            if agent.get("running")
            else "recorded only; no musical response until the agent is running"
        ),
    }


@mcp.tool()
def dj_prepare_next(
    direction: str,
    duration_bars: int = 32,
    target_deck: Literal["A", "B"] | None = None,
    bpm: float | None = None,
) -> dict[str, object]:
    """Generate and validate phrase-sized material onto the off-air deck without transitioning."""
    direction = direction.strip()
    if not direction:
        raise ValueError("direction must not be empty")
    if not 4 <= duration_bars <= 128:
        raise ValueError("duration_bars must be between 4 and 128")
    snapshot = _combined_state()
    _require_safe_creative_change(snapshot)
    state = snapshot["state"]
    assert isinstance(state, dict)
    transport = state["transport"]
    assert isinstance(transport, dict)
    resolved_bpm = float(bpm if bpm is not None else transport["bpm"])
    if not 40 <= resolved_bpm <= 240:
        raise ValueError("bpm must be between 40 and 240")
    duration_seconds = duration_bars * 4 * 60 / resolved_bpm
    if duration_seconds > 600:
        raise ValueError("requested bars exceed the 600-second generation ceiling at this BPM")
    deck = _target_deck(snapshot, target_deck)
    generation = _command(
        "generate",
        deck,
        "--prompt",
        direction,
        "--bpm",
        str(resolved_bpm),
        "--duration",
        str(duration_seconds),
        timeout=660,
    )
    try:
        analysis: dict[str, object] | None = _command("analyse", deck, timeout=120)
        validation = "analysed"
    except DJCommandError as exc:
        analysis = {"warning": str(exc)}
        validation = "generation succeeded; analysis unavailable"
    return {
        "prepared_deck": deck,
        "direction": direction,
        "duration_bars": duration_bars,
        "duration_seconds": duration_seconds,
        "bpm": resolved_bpm,
        "generation": generation,
        "analysis": analysis,
        "validation": validation,
        "transitioned": False,
    }


@mcp.tool()
def dj_schedule_transition(
    target_deck: Literal["A", "B"] | None = None,
    transition_bars: float = 8,
    phrase_bars: Literal[4, 8, 16, 32] = 4,
) -> dict[str, object]:
    """Schedule a prepared deck at the next phrase boundary; requires the local agent worker."""
    if not 0 < transition_bars <= 32:
        raise ValueError("transition_bars must be greater than 0 and at most 32")
    snapshot = _combined_state()
    _require_safe_creative_change(snapshot)
    runtime = snapshot["runtime"]
    agent = snapshot["agent"]
    state = snapshot["state"]
    assert isinstance(runtime, dict) and isinstance(agent, dict) and isinstance(state, dict)
    if not runtime.get("running"):
        raise DJCommandError("transition refused: audio runtime is not running")
    if not agent.get("running"):
        raise DJCommandError("transition refused: agent worker is not running to execute schedules")
    deck = _target_deck(snapshot, target_deck)
    decks = state["decks"]
    assert isinstance(decks, dict)
    target = decks[deck]
    assert isinstance(target, dict)
    if not target.get("audio_path") or target.get("status") not in {"prepared", "playing"}:
        raise DJCommandError(f"transition refused: deck {deck} has no prepared audio")
    scheduled = _command(
        "schedule",
        "crossfade",
        deck,
        "--at",
        f"next-{phrase_bars}",
        "--bars",
        str(transition_bars),
    )
    return {
        "target_deck": deck,
        "phrase_bars": phrase_bars,
        "transition_bars": transition_bars,
        "scheduled": scheduled,
    }


@mcp.tool()
def dj_review_recent_events(limit: int = 20) -> dict[str, object]:
    """Review recent concise operational events without reading private reasoning traces."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return _command("events", "--limit", str(limit))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
