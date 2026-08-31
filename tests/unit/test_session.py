from pathlib import Path

from dj.session import SessionStore


def test_session_round_trip_uses_machine_readable_state(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    created = store.create("test-session")
    created.future.estimated_seconds = 90
    store.save(created)
    loaded = store.load(create=False)
    assert loaded.session_id == "test-session"
    assert loaded.future.estimated_seconds == 90
    assert store.events().read()[0]["type"] == "session_created"

