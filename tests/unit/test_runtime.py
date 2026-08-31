import pytest

from dj.runtime import RuntimeController
from dj.session import SessionStore


def test_live_runtime_requires_a_prepared_local_deck(tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.create("empty")

    with pytest.raises(RuntimeError, match="prepare at least one local audio deck"):
        RuntimeController(store).start(test_mode=False)
