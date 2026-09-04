from __future__ import annotations

from typing import Any

from dj.codex_client import CodexAppServer


def test_thread_start_uses_app_server_sandbox_spelling(monkeypatch) -> None:
    client = CodexAppServer(executable="/usr/bin/false")
    requests: list[tuple[str, dict[str, Any]]] = []

    def rpc(method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        del timeout
        requests.append((method, params))
        return {"thread": {"id": "thread-1"}}

    monkeypatch.setattr(client, "_rpc", rpc)

    client.new_thread("gpt-test")

    method, params = requests[0]
    assert method == "thread/start"
    assert params["sandbox"] == "workspace-write"
    assert params["approvalPolicy"] == "never"
    assert params["model"] == "gpt-test"


def test_turn_uses_nested_workspace_write_policy_and_idempotency(monkeypatch) -> None:
    client = CodexAppServer(executable="/usr/bin/false")
    requests: list[tuple[str, dict[str, Any]]] = []

    def rpc(method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        del timeout
        requests.append((method, params))
        return {"turn": {"id": "turn-1", "status": "inProgress"}}

    monkeypatch.setattr(client, "_rpc", rpc)

    client.turn("thread-1", "Keep the music running")

    method, params = requests[0]
    assert method == "turn/start"
    assert params["sandboxPolicy"]["type"] == "workspaceWrite"
    assert params["sandboxPolicy"]["networkAccess"] is False
    assert params["clientUserMessageId"]


def test_read_uses_paginated_turn_api_and_preserves_compatibility(monkeypatch) -> None:
    client = CodexAppServer(executable="/usr/bin/false")
    requests: list[tuple[str, dict[str, Any]]] = []

    def rpc(method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        del timeout
        requests.append((method, params))
        if method == "thread/read":
            return {"thread": {"id": "thread-1", "turns": []}}
        return {
            "data": [
                {"id": "newer", "status": "completed"},
                {"id": "older", "status": "completed"},
            ],
            "nextCursor": "next",
        }

    monkeypatch.setattr(client, "_rpc", rpc)

    result = client.read("thread-1", limit=2)

    assert requests == [
        ("thread/read", {"threadId": "thread-1", "includeTurns": False}),
        (
            "thread/turns/list",
            {
                "threadId": "thread-1",
                "limit": 2,
                "sortDirection": "desc",
                "itemsView": "full",
            },
        ),
    ]
    assert [turn["id"] for turn in result["thread"]["turns"]] == ["older", "newer"]
    assert result["nextCursor"] == "next"
