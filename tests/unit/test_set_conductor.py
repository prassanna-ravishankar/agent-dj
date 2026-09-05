from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dj.config import settings
from dj.models import DeckStatus
from dj.session import SessionStore
from dj.set_conductor import SetConductor, SetStore, SetWorker, phase_for, translate_direction


def test_high_level_direction_becomes_stable_musical_prompt() -> None:
    phase, phase_direction = phase_for(0.65)
    prompt = translate_direction(
        "modern Indian house fusion",
        phase,
        phase_direction,
        "more tabla, less synth",
    )

    assert phase == "crest"
    assert "modern Indian house fusion" in prompt
    assert "more tabla, less synth" in prompt
    assert "stable full-range timbre" in prompt
    assert "no filter sweeps" in prompt


def test_steering_is_a_signal_trigger_not_a_polling_agent(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    store.create("set-test")
    set_store = SetStore(store)
    set_store.save({**set_store.idle(), "status": "running", "brief": "patient house"})
    conductor = SetConductor(store)
    monkeypatch.setattr(conductor, "_wake", lambda: None)

    result = conductor.steer("bring the hand percussion forward")

    assert result["ok"] is True
    assert set_store.pending(None)[-1]["text"] == "bring the hand percussion forward"
    assert result["hosted_tokens"] is False


def test_ending_conductor_never_stops_runtime(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    store.create("set-test")
    set_store = SetStore(store)
    set_store.save({**set_store.idle(), "status": "running", "brief": "patient house"})
    conductor = SetConductor(store)
    monkeypatch.setattr(conductor, "_stop_worker", lambda: None)

    result = conductor.end()

    assert result["set"]["status"] == "complete"
    assert store.events().read()[-1]["audio_continues"] is True


def _running_set(set_store: SetStore) -> dict[str, object]:
    now = datetime.now(UTC)
    return set_store.save(
        {
            **set_store.idle(),
            "status": "running",
            "brief": "patient Indian house",
            "started_at": now.isoformat(),
            "ends_at": (now + timedelta(minutes=90)).isoformat(),
            "next_cue_at": now.isoformat(),
            "activity": "ready",
        }
    )


def test_cue_steers_both_fallback_deck_and_primary_stream(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("set-test")
    state.future.estimated_seconds = 86_400
    state.stream.enabled = True
    state.decks["A"].status = DeckStatus.PLAYING
    state.decks["B"].status = DeckStatus.PREPARED
    store.save(state)
    set_store = SetStore(store)
    current = _running_set(set_store)
    calls: list[tuple[object, ...]] = []

    class Keeper:
        def __init__(self, *_: object) -> None:
            pass

        def prepare(self, **_: object) -> dict[str, object]:
            return {"ok": True, "prepared_deck": "B"}

    class Mixer:
        def stream_prompt(self, *args: object) -> None:
            calls.append(("prompt", *args))

        def crossfade(self, *args: object) -> None:
            calls.append(("crossfade", *args))

        def stream_weight(self, *args: object) -> None:
            calls.append(("weight", *args))

    monkeypatch.setattr("dj.set_conductor.DeckKeeper", Keeper)
    monkeypatch.setattr("dj.set_conductor.SuperColliderMixer", Mixer)
    monkeypatch.setattr("dj.set_conductor.RuntimeController.status", lambda _: {"running": True})
    worker = SetWorker()
    worker.controller = SetConductor(store)
    worker.store = set_store

    worker._advance(current, "bring the tabla forward")

    assert any(call[0] == "crossfade" for call in calls)
    assert any(call[:2] == ("prompt", 1) for call in calls)
    assert any(call[:3] == ("weight", 1, 1.0) for call in calls)
    assert store.load().stream.prompts[1].weight == 1
    assert "tabla" in set_store.load()["current_note"]


def test_hold_during_generation_cancels_audible_move(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("set-test")
    state.future.estimated_seconds = 86_400
    state.decks["A"].status = DeckStatus.PLAYING
    store.save(state)
    set_store = SetStore(store)
    current = _running_set(set_store)
    calls: list[tuple[object, ...]] = []

    class Keeper:
        def __init__(self, *_: object) -> None:
            pass

        def prepare(self, **_: object) -> dict[str, object]:
            latest = set_store.load()
            latest["status"] = "held"
            set_store.save(latest)
            return {"ok": True, "prepared_deck": "B"}

    class Mixer:
        def stream_prompt(self, *args: object) -> None:
            calls.append(("prompt", *args))

        def crossfade(self, *args: object) -> None:
            calls.append(("crossfade", *args))

    monkeypatch.setattr("dj.set_conductor.DeckKeeper", Keeper)
    monkeypatch.setattr("dj.set_conductor.SuperColliderMixer", Mixer)
    monkeypatch.setattr("dj.set_conductor.RuntimeController.status", lambda _: {"running": True})
    worker = SetWorker()
    worker.controller = SetConductor(store)
    worker.store = set_store

    worker._advance(current, "hold after this")

    assert not any(call[0] == "crossfade" for call in calls)
    assert store.events().read()[-1]["type"] == "set_cue_cancelled"


def test_generation_failure_backs_off_without_killing_the_set(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("set-test")
    state.future.estimated_seconds = 86_400
    store.save(state)
    set_store = SetStore(store)
    current = _running_set(set_store)

    class Keeper:
        def __init__(self, *_: object) -> None:
            pass

        def prepare(self, **_: object) -> dict[str, object]:
            raise RuntimeError("generator unavailable")

    class Mixer:
        def stream_prompt(self, *_: object) -> None:
            pass

    monkeypatch.setattr("dj.set_conductor.DeckKeeper", Keeper)
    monkeypatch.setattr("dj.set_conductor.SuperColliderMixer", Mixer)
    monkeypatch.setattr("dj.set_conductor.RuntimeController.status", lambda _: {"running": True})
    worker = SetWorker()
    worker.controller = SetConductor(store)
    worker.store = set_store

    worker._advance(current)

    updated = set_store.load()
    assert updated["status"] == "running"
    assert updated["activity"] == "retrying"
    assert datetime.fromisoformat(updated["next_cue_at"]) > datetime.now(UTC)


def test_osc_control_failure_backs_off_without_killing_the_set(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("set-test")
    state.future.estimated_seconds = 86_400
    store.save(state)
    set_store = SetStore(store)
    current = _running_set(set_store)

    class Mixer:
        def stream_prompt(self, *_: object) -> None:
            raise OSError("OSC unavailable")

    monkeypatch.setattr("dj.set_conductor.SuperColliderMixer", Mixer)
    monkeypatch.setattr("dj.set_conductor.RuntimeController.status", lambda _: {"running": True})
    worker = SetWorker()
    worker.controller = SetConductor(store)
    worker.store = set_store

    worker._advance(current)

    updated = set_store.load()
    assert updated["status"] == "running"
    assert updated["activity"] == "retrying"
    assert store.events().read()[-1]["type"] == "set_cue_failed"


def test_first_start_prepares_deck_a_inside_the_one_action(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    store.create("set-test")
    prepared: list[str] = []

    class Keeper:
        def __init__(self, *_: object) -> None:
            pass

        def prepare(self, **_: object) -> dict[str, object]:
            audio = tmp_path / "safety-a.wav"
            audio.write_bytes(b"safe")
            state = store.load()
            state.decks["A"].audio_path = str(audio)
            state.decks["A"].status = DeckStatus.PREPARED
            store.save(state)
            prepared.append("A")
            return {"ok": True, "prepared_deck": "A"}

    class Runtime:
        def __init__(self, *_: object) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {"running": False}

        def start(self, **_: object) -> dict[str, object]:
            return {"running": True}

    monkeypatch.setattr("dj.set_conductor.DeckKeeper", Keeper)
    monkeypatch.setattr("dj.set_conductor.RuntimeController", Runtime)
    conductor = SetConductor(store)
    monkeypatch.setattr(conductor, "_start_worker", lambda **_: None)

    conductor.start_set("warm Indian house", 90)

    assert prepared == ["A"]
    assert conductor.set_store.load()["status"] == "running"


def test_failed_runtime_start_does_not_publish_an_active_set(tmp_path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("set-test")
    audio = tmp_path / "safety-a.wav"
    audio.write_bytes(b"safe")
    state.decks["A"].audio_path = str(audio)
    state.stream.prompts[2].text = "existing direction"
    state.stream.prompts[2].weight = 1
    store.save(state)

    class Runtime:
        def __init__(self, *_: object) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {"running": False}

        def start(self, **_: object) -> dict[str, object]:
            raise RuntimeError("audio unavailable")

    monkeypatch.setattr("dj.set_conductor.RuntimeController", Runtime)
    conductor = SetConductor(store)

    try:
        conductor.start_set("new direction", 90)
    except RuntimeError as exc:
        assert str(exc) == "audio unavailable"
    else:
        raise AssertionError("startup failure should escape")

    assert conductor.set_store.load()["status"] == "idle"
    assert store.load().stream.prompts[2].weight == 1
