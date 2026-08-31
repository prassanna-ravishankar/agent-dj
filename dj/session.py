from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from dj.config import settings
from dj.events import EventLog
from dj.models import DJState


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.sessions_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.current_file = self.root / ".current"

    def create(self, session_id: str | None = None) -> DJState:
        session_id = session_id or datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
        directory = self.root / session_id
        (directory / "renders").mkdir(parents=True, exist_ok=True)
        (directory / "analysis").mkdir(parents=True, exist_ok=True)
        state = DJState(session_id=session_id)
        self.save(state)
        self.current_file.write_text(session_id, encoding="utf-8")
        self.events(session_id).append("session_created", session_id=session_id)
        return state

    def current_id(self) -> str | None:
        return self.current_file.read_text().strip() if self.current_file.exists() else None

    def load(self, session_id: str | None = None, *, create: bool = True) -> DJState:
        session_id = session_id or self.current_id()
        if session_id is None:
            if create:
                return self.create()
            raise FileNotFoundError("no active session")
        path = self.root / session_id / "state.json"
        if not path.exists():
            raise FileNotFoundError(f"session not found: {session_id}")
        return DJState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: DJState) -> None:
        directory = self.root / state.session_id
        directory.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now(UTC)
        (directory / "state.json").write_text(
            state.model_dump_json(indent=2), encoding="utf-8"
        )

    def events(self, session_id: str | None = None) -> EventLog:
        resolved = session_id or self.current_id()
        if resolved is None:
            raise FileNotFoundError("no active session")
        return EventLog(self.root / resolved / "events.jsonl")

    def append_decision(self, session_id: str, decision: dict[str, object]) -> None:
        path = self.root / session_id / "decisions.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(decision, default=str, separators=(",", ":")) + "\n")
