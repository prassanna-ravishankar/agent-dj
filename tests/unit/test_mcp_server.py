from __future__ import annotations

import asyncio
from typing import Any

from mcp import Client

from dj import mcp_server


def _state() -> dict[str, Any]:
    return {
        "session_id": "mcp-test",
        "status": "live",
        "transport": {"playing": True, "bpm": 120.0},
        "decks": {
            "A": {"status": "playing", "audio_path": "/tmp/a.wav"},
            "B": {"status": "prepared", "audio_path": "/tmp/b.wav"},
        },
        "future": {"covered_until_bar": 64, "estimated_seconds": 86_400.0},
    }


def test_mcp_lists_only_the_agent_sized_tools() -> None:
    async def exercise() -> list[str]:
        async with Client(mcp_server.mcp) as client:
            result = await client.list_tools()
            return [tool.name for tool in result.tools]

    assert asyncio.run(exercise()) == [
        "dj_inspect",
        "dj_submit_observation",
        "dj_prepare_next",
        "dj_schedule_transition",
        "dj_stream_set_prompt",
        "dj_stream_schedule_morph",
        "dj_stream_control",
        "dj_review_recent_events",
    ]


def test_inspect_returns_explicit_safety_context(monkeypatch) -> None:
    def command(*arguments: str, timeout: float = 30.0) -> dict[str, Any]:
        del timeout
        if arguments == ("state",):
            return _state()
        if arguments == ("status",):
            return {"ok": True, "running": True, "pid": 10, "local_only": True}
        if arguments == ("agent", "status"):
            return {"ok": True, "running": True, "pid": 11, "local_only": True}
        raise AssertionError(arguments)

    monkeypatch.setattr(mcp_server, "_command", command)

    async def exercise() -> dict[str, Any]:
        async with Client(mcp_server.mcp) as client:
            result = await client.call_tool("dj_inspect")
            assert result.structured_content is not None
            return result.structured_content

    payload = asyncio.run(exercise())
    assert payload["safety"] == {
        "coverage": "safe",
        "future_seconds": 86_400.0,
        "safe_loop": True,
        "on_air_deck": "A",
        "music_must_not_stop": True,
    }


def test_prepare_next_uses_the_off_air_deck_and_certified_cli(monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []

    def command(*arguments: str, timeout: float = 30.0) -> dict[str, Any]:
        del timeout
        if arguments == ("state",):
            return _state()
        if arguments == ("status",):
            return {"ok": True, "running": True, "pid": 10, "local_only": True}
        if arguments == ("agent", "status"):
            return {"ok": True, "running": True, "pid": 11, "local_only": True}
        commands.append(arguments)
        if arguments[0] == "analyse":
            return {"duration_seconds": 64.0, "peak_dbfs": -1.0}
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_command", command)

    async def exercise() -> dict[str, Any]:
        async with Client(mcp_server.mcp) as client:
            result = await client.call_tool(
                "dj_prepare_next",
                {"direction": "patient percussion", "duration_bars": 32},
            )
            assert result.structured_content is not None
            return result.structured_content

    payload = asyncio.run(exercise())
    assert payload["prepared_deck"] == "B"
    assert commands[0][:2] == ("generate", "B")
    assert commands[1] == ("analyse", "B")


def test_critical_live_session_without_playing_buffer_refuses_creative_work(
    monkeypatch,
) -> None:
    state = _state()
    state["future"]["estimated_seconds"] = 10.0
    state["decks"]["A"]["status"] = "prepared"
    commands: list[tuple[str, ...]] = []

    def command(*arguments: str, timeout: float = 30.0) -> dict[str, Any]:
        del timeout
        if arguments == ("state",):
            return state
        if arguments == ("status",):
            return {"ok": True, "running": True, "pid": 10, "local_only": True}
        if arguments == ("agent", "status"):
            return {"ok": True, "running": True, "pid": 11, "local_only": True}
        commands.append(arguments)
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_command", command)

    async def exercise() -> bool:
        async with Client(mcp_server.mcp) as client:
            result = await client.call_tool(
                "dj_prepare_next",
                {"direction": "creative detour", "duration_bars": 32},
            )
            return result.is_error

    assert asyncio.run(exercise()) is True
    assert commands == []


def test_stream_morph_uses_phrase_scheduled_certified_command(monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []

    def command(*arguments: str, timeout: float = 30.0) -> dict[str, Any]:
        del timeout
        if arguments == ("state",):
            return _state()
        if arguments == ("status",):
            return {"ok": True, "running": True, "pid": 10, "local_only": True}
        if arguments == ("agent", "status"):
            return {"ok": True, "running": True, "pid": 11, "local_only": True}
        commands.append(arguments)
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_command", command)

    async def exercise() -> dict[str, Any]:
        async with Client(mcp_server.mcp) as client:
            result = await client.call_tool(
                "dj_stream_schedule_morph",
                {"slot": 2, "weight": 0.75, "morph_bars": 8, "phrase_bars": 16},
            )
            assert result.structured_content is not None
            return result.structured_content

    payload = asyncio.run(exercise())
    assert payload["slot"] == 2
    assert commands == [
        (
            "stream", "schedule", "2", "--weight", "0.75",
            "--at", "next-16", "--bars", "8.0",
        )
    ]
