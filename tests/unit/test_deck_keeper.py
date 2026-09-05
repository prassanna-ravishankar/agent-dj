from __future__ import annotations

from dj.agent import AgentController
from dj.config import settings
from dj.deck_keeper import DeckKeeper
from dj.generator.fake import FakeGenerator
from dj.models import DeckName, DeckStatus
from dj.session import SessionStore


def test_trigger_prepares_only_the_off_air_deck_without_starting_agent(
    tmp_path, monkeypatch
) -> None:
    sessions = tmp_path / "sessions"
    monkeypatch.setattr(settings, "sessions_dir", sessions)
    store = SessionStore(sessions)
    state = store.create("keeper-test")
    state.decks[DeckName.A].status = DeckStatus.PLAYING
    state.decks[DeckName.A].audio_path = "/safe/a.wav"
    state.decks[DeckName.A].prompt = "modern Indian house, steady tabla"
    state.decks[DeckName.B].status = DeckStatus.PREPARED
    state.decks[DeckName.B].audio_path = "/safe/old-b.wav"
    store.save(state)

    result = DeckKeeper(store, generator=FakeGenerator(440)).prepare(duration=0.25)

    updated = store.load()
    assert result["ok"] is True
    assert result["prepared_deck"] == "B"
    assert result["agent_started"] is False
    assert result["watching"] is False
    assert updated.decks[DeckName.A].audio_path == "/safe/a.wav"
    assert updated.decks[DeckName.A].status is DeckStatus.PLAYING
    assert updated.decks[DeckName.B].status is DeckStatus.PREPARED
    assert updated.decks[DeckName.B].audio_path != "/safe/old-b.wav"
    assert "next-deck variation" in (updated.decks[DeckName.B].prompt or "")
    assert AgentController().status()["running"] is False
    assert store.events().read()[-1]["type"] == "deck_keeper_ready"


def test_derived_direction_does_not_grow_repeated_suffixes(tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions")
    state = store.create("keeper-direction")
    state.decks[DeckName.B].status = DeckStatus.PLAYING
    state.decks[DeckName.B].prompt = (
        "modern house, next-deck variation: old suffix, coherent with the current set"
    )

    direction = DeckKeeper.derive_direction(state, DeckName.A)

    assert direction.count("next-deck variation:") == 1
    assert direction.startswith("modern house, next-deck variation:")


def test_validation_rejects_silence_and_clipping() -> None:
    assert DeckKeeper.validate({"ok": True, "rms": 0.0, "peak_dbfs": -20}) == (
        False,
        "generated audio is silent",
    )
    assert DeckKeeper.validate({"ok": True, "rms": 0.1, "peak_dbfs": 0.1}) == (
        False,
        "generated audio clips above 0 dBFS",
    )
