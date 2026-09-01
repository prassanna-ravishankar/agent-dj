from __future__ import annotations

import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from dj import web_server
from dj.config import settings
from dj.session import SessionStore
from dj.web_server import app


def test_snapshot_preserves_nullable_measurements_and_safe_sentinel(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("web-test")
    state.future.estimated_seconds = 86_400
    state.master.peak_dbfs = None
    store.save(state)
    store.events().append("test_event", value=0)
    decision = {
        "observation_id": "o1",
        "goal": "hold",
        "evidence": ["safe"],
        "target_deck": "B",
        "prompt": "patient house",
        "transition_bars": 16,
        "energy_delta": 0,
    }
    (sessions / "web-test" / "decisions.jsonl").write_text(
        json.dumps({"decision": decision}) + "\n{partial", encoding="utf-8"
    )

    with TestClient(app) as client:
        response = client.get("/api/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["demo"] is False
    assert payload["state"]["future"]["estimated_seconds"] == 86_400
    assert payload["state"]["master"]["peak_dbfs"] is None
    assert payload["decisions"] == [decision]
    assert any(event["type"] == "test_event" for event in payload["events"])


def test_invalid_web_command_payload_is_a_400(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    SessionStore(sessions).create("web-test")

    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={"deck": "C", "prompt": "", "bpm": 500, "duration": 0},
        )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_command_endpoints_translate_to_certified_cli_without_real_io(
    tmp_path, monkeypatch
) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    SessionStore(sessions).create("web-test")
    run_dj = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(web_server, "_run_dj", run_dj)

    commands = [
        ("/api/generate", {"deck": "B", "prompt": "patient house", "bpm": 124, "duration": 16}),
        ("/api/play", {"deck": "B"}),
        ("/api/crossfade", {"target": "B", "bars": 16}),
        ("/api/gain", {"deck": "B", "gain_db": -6}),
        ("/api/filter", {"deck": "B", "kind": "lowpass", "frequency_hz": 8000}),
        ("/api/record", {"action": "start"}),
        ("/api/feedback", {"kind": "love"}),
    ]

    with TestClient(app) as client:
        responses = [client.post(path, json=payload) for path, payload in commands]

    assert all(response.status_code == 204 for response in responses)
    assert [call.args[0] for call in run_dj.await_args_list] == [
        "generate", "play", "crossfade", "gain", "filter", "record", "feedback"
    ]
