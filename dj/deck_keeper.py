from __future__ import annotations

import asyncio
import fcntl
import os
from datetime import UTC, datetime
from typing import Any

from dj.analysis.base import Analyzer
from dj.analysis.local import LocalAnalyzer
from dj.generator.base import Generator
from dj.generator.magenta_live import MagentaLiveGenerator
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckName, DeckStatus, DJState
from dj.runtime import RuntimeController
from dj.session import SessionStore


class DeckKeeperBusy(RuntimeError):
    pass


class DeckKeeper:
    """One triggered off-air preparation job. It never watches or starts another process."""

    def __init__(
        self,
        store: SessionStore | None = None,
        generator: Generator | None = None,
        analyzer: Analyzer | None = None,
    ) -> None:
        self.store = store or SessionStore()
        self.generator = generator or MagentaLiveGenerator()
        self.analyzer = analyzer or LocalAnalyzer()

    @staticmethod
    def playing_deck(state: DJState) -> DeckName | None:
        return next(
            (name for name, deck in state.decks.items() if deck.status is DeckStatus.PLAYING),
            None,
        )

    @classmethod
    def target_deck(cls, state: DJState) -> DeckName:
        playing = cls.playing_deck(state)
        if playing is DeckName.A:
            return DeckName.B
        if playing is DeckName.B:
            return DeckName.A
        # A fresh stopped session prepares A first; otherwise preserve A and fill B.
        return DeckName.B if state.decks[DeckName.A].audio_path else DeckName.A

    @classmethod
    def derive_direction(cls, state: DJState, target: DeckName) -> str:
        playing = cls.playing_deck(state)
        source = state.decks[playing].prompt if playing else None
        if not source:
            active = sorted(state.stream.prompts, key=lambda item: item.weight, reverse=True)
            source = next((item.text for item in active if item.text.strip()), "modern house")
        # Do not let a derived suffix grow every time the keeper is triggered.
        base = source.split(", next-deck variation:", 1)[0].strip().rstrip(",")
        variation = (
            "deeper modal harmony, supple hand percussion, patient bass movement"
            if target is DeckName.A
            else "brighter melodic answers, crisp syncopation, controlled forward lift"
        )
        return (
            f"{base}, next-deck variation: {variation}, coherent with the current set, "
            "instrumental, stable full-range timbre"
        )[:1000]

    @staticmethod
    def validate(analysis: dict[str, Any]) -> tuple[bool, str]:
        if not analysis.get("ok"):
            return False, str(analysis.get("error", "analysis failed"))
        if float(analysis.get("rms", 0.0)) <= 1e-5:
            return False, "generated audio is silent"
        if float(analysis.get("peak_dbfs", 1.0)) > 0.0:
            return False, "generated audio clips above 0 dBFS"
        return True, "finite, non-silent, and unclipped"

    def prepare(
        self,
        direction: str | None = None,
        duration: float = 64.0,
        bpm: float | None = None,
    ) -> dict[str, Any]:
        state = self.store.load(create=False)
        session_dir = self.store.root / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        lock_path = session_dir / ".deck-keeper.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeckKeeperBusy("a deck preparation trigger is already running") from exc
            return self._prepare_locked(state, direction, duration, bpm)
        finally:
            os.close(lock_fd)

    def _prepare_locked(
        self,
        state: DJState,
        direction: str | None,
        duration: float,
        bpm: float | None,
    ) -> dict[str, Any]:
        events = self.store.events(state.session_id)
        session_dir = self.store.root / state.session_id
        runtime_running = bool(RuntimeController(self.store).status()["running"])
        playing = self.playing_deck(state)
        if runtime_running and playing is None:
            raise RuntimeError("preparation refused: live runtime has no identified playing deck")
        target = self.target_deck(state)
        if state.decks[target].status is DeckStatus.PREPARING:
            raise DeckKeeperBusy(f"deck {target.value} is already being prepared")
        resolved_bpm = bpm if bpm is not None else state.transport.bpm
        prompt = direction.strip() if direction and direction.strip() else self.derive_direction(state, target)
        events.append(
            "deck_keeper_triggered",
            target_deck=target,
            source_deck=playing,
            direction=prompt,
            duration_seconds=duration,
            starts_agent=False,
            watching=False,
            local_only=True,
        )
        output = (
            session_dir / "generated" /
            f"keeper-{target.value}-{datetime.now(UTC).strftime('%H%M%S')}.wav"
        )
        output.parent.mkdir(parents=True, exist_ok=True)

        async def generate() -> dict[str, Any]:
            await self.generator.prepare(prompt, resolved_bpm)
            await self.generator.start()
            try:
                await self.generator.render(output, duration)
                return await self.generator.health()
            finally:
                await self.generator.stop()

        try:
            health = asyncio.run(generate())
            analysis = self.analyzer.analyse(output)
            valid, reason = self.validate(analysis)
            if not valid:
                events.append(
                    "deck_keeper_rejected", target_deck=target, reason=reason,
                    path=str(output), audio_unchanged=True,
                )
                return {
                    "ok": False,
                    "prepared_deck": target,
                    "reason": reason,
                    "analysis": analysis,
                    "audio_unchanged": True,
                }

            latest = self.store.load(create=False)
            latest_playing = self.playing_deck(latest)
            runtime_now = bool(RuntimeController(self.store).status()["running"])
            if runtime_now and latest_playing is target:
                events.append(
                    "deck_keeper_aborted", target_deck=target,
                    reason="target deck came on air during generation", audio_unchanged=True,
                )
                return {
                    "ok": False,
                    "prepared_deck": target,
                    "reason": "target deck came on air during generation",
                    "analysis": analysis,
                    "audio_unchanged": True,
                }
            if runtime_now:
                SuperColliderMixer().load(target, output)
            deck = latest.decks[target]
            deck.status = DeckStatus.PREPARED
            deck.source = "magenta"
            deck.prompt = prompt
            deck.audio_path = str(output)
            deck.duration_seconds = duration
            deck.energy = None
            if any(item.audio_path for item in latest.decks.values()):
                latest.future.estimated_seconds = 86_400
            self.store.save(latest)
            ready = events.append(
                "deck_keeper_ready", target_deck=target, source_deck=latest_playing,
                direction=prompt, path=str(output), validation=reason,
                realtime_factor=health.get("realtime_factor"), transitioned=False,
                agent_started=False, local_only=True,
            )
            return {
                "ok": True,
                "prepared_deck": target,
                "source_deck": latest_playing,
                "direction": prompt,
                "duration_seconds": duration,
                "bpm": resolved_bpm,
                "analysis": analysis,
                "validation": reason,
                "transitioned": False,
                "agent_started": False,
                "watching": False,
                "event": ready,
            }
        except Exception as exc:
            events.append(
                "deck_keeper_failed", target_deck=target, error=str(exc), audio_unchanged=True,
            )
            raise
