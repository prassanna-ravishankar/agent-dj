from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dj.config import settings
from dj.deck_keeper import DeckKeeper
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckStatus
from dj.runtime import RuntimeController
from dj.session import SessionStore
from dj.transport import Transport

PHASES = (
    (0.00, "arrival", "patient entrance, open space, establish the groove without rushing"),
    (0.15, "gather", "more rhythmic conversation, warmer bass movement, gradual lift"),
    (0.38, "rise", "confident forward motion, denser percussion, memorable melodic answers"),
    (0.62, "crest", "peak dance-floor energy, decisive drums, bright controlled release"),
    (0.82, "return", "reduce density with grace, deeper harmony, retain pulse and continuity"),
    (0.94, "landing", "resolved final passage, spacious percussion, warm unhurried close"),
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.isoformat()


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def phase_for(progress: float) -> tuple[str, str]:
    selected = PHASES[0][1:]
    for threshold, name, direction in PHASES:
        if progress >= threshold:
            selected = (name, direction)
    return selected


def translate_direction(brief: str, phase: str, phase_direction: str, steering: str = "") -> str:
    """Turn a human brief into a stable MRT2/deck prompt without an LLM call."""
    steer = steering.strip()
    parts = [
        brief.strip(),
        f"{phase} passage: {phase_direction}",
    ]
    if steer:
        parts.append(f"DJ direction from the room: {steer}")
    parts.extend(
        (
            "coherent continuation of one long set",
            "instrumental, stable full-range timbre",
            "dry clear transients, no filter sweeps, phaser, flanger, pumping pads, or dub wobble",
        )
    )
    return ", ".join(parts)[:1000]


def describe_direction(phase: str, phase_direction: str, steering: str = "") -> str:
    return f"{phase.title()} — {steering.strip() or phase_direction}"


class SetStore:
    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()

    @property
    def path(self) -> Path:
        state = self.store.load(create=False)
        return self.store.root / state.session_id / "set.json"

    @property
    def queue_path(self) -> Path:
        return self.path.with_name("set-steering.jsonl")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.idle()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self.idle(), **value} if isinstance(value, dict) else self.idle()
        except (OSError, json.JSONDecodeError):
            return self.idle()

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {**value, "updated_at": iso(utc_now())}
        temporary = self.path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return value

    def enqueue(self, text: str) -> dict[str, Any]:
        item = {"id": str(uuid.uuid4()), "text": text.strip(), "created_at": iso(utc_now())}
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, separators=(",", ":")) + "\n")
        return item

    def pending(self, after_id: str | None) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        items = [json.loads(line) for line in self.queue_path.read_text().splitlines() if line]
        if after_id is None:
            return items
        for index, item in enumerate(items):
            if item.get("id") == after_id:
                return items[index + 1 :]
        return items

    def latest_id(self) -> str | None:
        items = self.pending(None)
        return str(items[-1]["id"]) if items else None

    @staticmethod
    def idle() -> dict[str, Any]:
        return {
            "status": "idle",
            "brief": "",
            "duration_minutes": 90,
            "started_at": None,
            "ends_at": None,
            "phase": "idle",
            "progress": 0.0,
            "current_direction": None,
            "next_direction": None,
            "current_note": None,
            "next_note": None,
            "next_cue_at": None,
            "last_steering": None,
            "cue_index": 0,
            "local_only": True,
            "hosted_tokens": False,
            "last_trigger_id": None,
            "activity": "idle",
        }


class SetConductor:
    """Event-driven local set steward. Audio remains independent of this process."""

    def __init__(self, store: SessionStore | None = None) -> None:
        self.session_store = store or SessionStore()
        self.set_store = SetStore(self.session_store)
        self.ready_file = settings.sessions_dir / ".set-conductor-ready"
        self.pid_file = settings.sessions_dir / ".set-conductor-pid"

    def status(self) -> dict[str, Any]:
        pid = self._pid()
        running = bool(pid and self._alive(pid) and self.ready_file.exists())
        return {
            "ok": True,
            "running": running,
            "pid": pid if running else None,
            "local_only": True,
            "hosted_tokens": False,
            "set": self._refreshed_set(),
        }

    def start_set(
        self, brief: str, duration_minutes: int = 90, test_mode: bool = False
    ) -> dict[str, Any]:
        brief = brief.strip()
        if not brief:
            raise ValueError("give the set a musical direction")
        if self.status()["running"]:
            raise RuntimeError("a steered set is already running")
        state = self.session_store.load(create=False)
        runtime = RuntimeController(self.session_store)
        runtime_was_running = bool(runtime.status()["running"])
        if runtime_was_running and state.future.estimated_seconds < 90:
            if state.future.estimated_seconds < 30:
                SuperColliderMixer().stream_force_fallback(True)
                state.stream.force_fallback = True
                self.session_store.save(state)
            raise RuntimeError("live future coverage must be safe before starting a creative set")
        started = utc_now()
        phase, phase_direction = phase_for(0)
        direction = translate_direction(brief, phase, phase_direction)
        startup = state.decks["A"]
        if not startup.audio_path or not Path(startup.audio_path).exists():
            if runtime_was_running:
                raise RuntimeError("live startup deck A is missing; audio was left unchanged")
            prepared = DeckKeeper(self.session_store).prepare(
                direction=direction, duration=64, bpm=state.transport.bpm
            )
            if not prepared.get("ok") or str(prepared.get("prepared_deck")) != "A":
                raise RuntimeError("could not prepare startup safety deck A")
            state = self.session_store.load(create=False)
        performance = {
            **SetStore.idle(),
            "status": "running",
            "brief": brief,
            "duration_minutes": duration_minutes,
            "started_at": iso(started),
            "ends_at": iso(started + timedelta(minutes=duration_minutes)),
            "phase": phase,
            "current_direction": direction,
            "next_direction": translate_direction(brief, "gather", PHASES[1][2]),
            "current_note": describe_direction(phase, phase_direction),
            "next_note": describe_direction("gather", PHASES[1][2]),
            "next_cue_at": iso(started + timedelta(minutes=min(8, max(2, duration_minutes / 10)))),
            "last_trigger_id": self.set_store.latest_id(),
            "activity": "ready",
        }

        # An explicit Start set action authorizes audio startup. Seed the guarded stream first.
        original_stream = state.stream.model_copy(deep=True)
        state.stream.prompts[0].text = direction
        for prompt in state.stream.prompts:
            prompt.weight = 1.0 if prompt.slot == 0 else 0.0
        state.stream.enabled = True
        state.stream.force_fallback = False
        self.session_store.save(state)
        try:
            if not runtime_was_running:
                runtime.start(test_mode=test_mode)
            else:
                mixer = SuperColliderMixer()
                mixer.stream_prompt(0, direction, 1.0)
                for prompt in state.stream.prompts:
                    mixer.stream_weight(prompt.slot, prompt.weight, 8.0)
                mixer.stream_force_fallback(False)
                mixer.stream_enable(True)
        except Exception:
            latest = self.session_store.load(create=False)
            latest.stream = original_stream
            self.session_store.save(latest)
            raise

        # The requested duration measures audible runtime, not first-run preparation/model startup.
        started = utc_now()
        performance["started_at"] = iso(started)
        performance["ends_at"] = iso(started + timedelta(minutes=duration_minutes))
        performance["next_cue_at"] = iso(
            started + timedelta(minutes=min(8, max(2, duration_minutes / 10)))
        )
        self.set_store.save(performance)
        try:
            self._start_worker(test_mode=test_mode)
        except Exception as exc:
            performance["status"] = "interrupted"
            performance["activity"] = "conductor-failed"
            self.set_store.save(performance)
            self.session_store.events().append(
                "set_conductor_failed", error=str(exc), audio_continues=True
            )
            raise RuntimeError(
                "audio is playing safely, but the set conductor failed to start"
            ) from exc
        self.session_store.events().append(
            "set_started",
            brief=brief,
            duration_minutes=duration_minutes,
            conductor="event-driven-local",
            hosted_tokens=False,
        )
        return self.status()

    def steer(self, text: str) -> dict[str, Any]:
        current = self.set_store.load()
        if current.get("status") not in {"running", "held"}:
            raise RuntimeError("start a set before steering it")
        item = self.set_store.enqueue(text)
        current["last_steering"] = text.strip()
        current["next_note"] = f"Queued — {text.strip()}"
        current["activity"] = "queued"
        self.set_store.save(current)
        self._wake()
        self.session_store.events().append("set_steered", steering=text.strip(), trigger=item["id"])
        return {"ok": True, "trigger": item, **self.status()}

    def hold(self, held: bool = True) -> dict[str, Any]:
        current = self.set_store.load()
        if current.get("status") not in {"running", "held"}:
            raise RuntimeError("no set is running")
        current["status"] = "held" if held else "running"
        current["activity"] = "held" if held else "ready"
        self.set_store.save(current)
        self._wake()
        self.session_store.events().append(
            "set_held" if held else "set_resumed", audio_continues=True
        )
        return self.status()

    def end(self) -> dict[str, Any]:
        self._stop_worker()
        current = self.set_store.load()
        current["status"] = "complete"
        current["next_cue_at"] = None
        current["next_direction"] = None
        current["next_note"] = None
        current["activity"] = "complete"
        self.set_store.save(current)
        self.session_store.events().append("set_conductor_ended", audio_continues=True)
        return self.status()

    def _start_worker(self, test_mode: bool) -> None:
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)
        args = [sys.executable, "-m", "dj.set_conductor", "--run"]
        if test_mode:
            args.append("--test-mode")
        log = (settings.sessions_dir / "set-conductor.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            args,
            cwd=settings.project_root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.ready_file.exists():
                return
            if process.poll() is not None:
                raise RuntimeError(f"set conductor exited; inspect {log.name}")
            time.sleep(0.05)
        process.terminate()
        raise TimeoutError(f"set conductor did not become ready; inspect {log.name}")

    def _stop_worker(self) -> None:
        pid = self._pid()
        if pid and self._alive(pid):
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and self._alive(pid) and self.ready_file.exists():
                time.sleep(0.05)
            if self._alive(pid):
                os.kill(pid, signal.SIGKILL)
        self.ready_file.unlink(missing_ok=True)
        self.pid_file.unlink(missing_ok=True)

    def _wake(self) -> None:
        pid = self._pid()
        if not pid or not self._alive(pid):
            raise RuntimeError("the set conductor is not running; audio is unaffected")
        os.kill(pid, signal.SIGUSR1)

    def _refreshed_set(self) -> dict[str, Any]:
        value = self.set_store.load()
        started = parse_time(value.get("started_at"))
        ends = parse_time(value.get("ends_at"))
        if started and ends:
            span = max(1, (ends - started).total_seconds())
            value["progress"] = min(1.0, max(0.0, (utc_now() - started).total_seconds() / span))
        return value

    def _pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text()) if self.pid_file.exists() else None
        except ValueError:
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class SetWorker:
    def __init__(self, test_mode: bool = False) -> None:
        self.controller = SetConductor()
        self.store = self.controller.set_store
        self.test_mode = test_mode
        self.wake = threading.Event()
        self.stopping = False

    def run(self) -> None:
        signal.signal(signal.SIGUSR1, lambda *_: self.wake.set())
        signal.signal(signal.SIGTERM, self._stop)
        self.controller.pid_file.write_text(str(os.getpid()), encoding="utf-8")
        self.controller.ready_file.write_text("ready", encoding="utf-8")
        try:
            while not self.stopping:
                current = self.store.load()
                if current.get("status") == "running":
                    self._process_steering(current)
                    current = self.store.load()
                    due = parse_time(current.get("next_cue_at"))
                    ends = parse_time(current.get("ends_at"))
                    now = utc_now()
                    if ends and now >= ends:
                        current["status"] = "complete"
                        current["next_cue_at"] = None
                        current["next_direction"] = None
                        current["next_note"] = None
                        current["activity"] = "complete"
                        self.store.save(current)
                        self.controller.session_store.events().append(
                            "set_completed", audio_continues=True
                        )
                        self.stopping = True
                    elif due and now >= due:
                        self._advance(current)
                current = self.store.load()
                due = parse_time(current.get("next_cue_at"))
                timeout = max(0.1, (due - utc_now()).total_seconds()) if due else None
                self.wake.wait(timeout=timeout)
                self.wake.clear()
        except Exception as exc:  # noqa: BLE001 — unexpected conductor failure must be recorded
            current = self.store.load()
            current["status"] = "interrupted"
            current["activity"] = "conductor-failed"
            current["next_note"] = "Conductor stopped unexpectedly; current audio is unchanged"
            self.store.save(current)
            self.controller.session_store.events().append(
                "set_conductor_failed", error=str(exc), audio_unchanged=True
            )
        finally:
            self.controller.ready_file.unlink(missing_ok=True)
            self.controller.pid_file.unlink(missing_ok=True)

    def _stop(self, *_: object) -> None:
        self.stopping = True
        self.wake.set()

    def _process_steering(self, current: dict[str, Any]) -> None:
        for item in self.store.pending(current.get("last_trigger_id")):
            current["last_trigger_id"] = item["id"]
            self._advance(current, str(item["text"]))
            current = self.store.load()

    def _advance(self, current: dict[str, Any], steering: str = "") -> None:
        state = self.controller.session_store.load(create=False)
        if state.future.estimated_seconds < 30:
            if RuntimeController(self.controller.session_store).status()["running"]:
                SuperColliderMixer().stream_force_fallback(True)
                state.stream.force_fallback = True
                self.controller.session_store.save(state)
            self.controller.session_store.events().append(
                "set_cue_refused",
                reason="critical future coverage",
                fallback_requested=True,
                audio_unchanged=True,
            )
            current["status"] = "held"
            current["activity"] = "held-for-safety"
            current["next_cue_at"] = None
            current["next_note"] = "Safety hold — future coverage needs manual recovery"
            self.store.save(current)
            return
        started = parse_time(current.get("started_at")) or utc_now()
        ends = parse_time(current.get("ends_at")) or (started + timedelta(minutes=90))
        progress = min(
            1.0,
            max(
                0.0,
                (utc_now() - started).total_seconds() / max(1, (ends - started).total_seconds()),
            ),
        )
        phase, phase_direction = phase_for(progress)
        direction = translate_direction(current["brief"], phase, phase_direction, steering)
        note = describe_direction(phase, phase_direction, steering)
        current.update(
            {
                "phase": phase,
                "next_direction": direction,
                "next_note": note,
                "last_steering": steering or current.get("last_steering"),
                "activity": "preparing",
            }
        )
        self.store.save(current)

        if not self.test_mode:
            try:
                self._land_cue(current, state, direction, note, phase, steering)
            except Exception as exc:  # noqa: BLE001 — control failure must back off, never kill music
                self.controller.session_store.events().append(
                    "set_cue_failed", error=str(exc), recovery="deferred"
                )
                self._defer(current, "Control path failed — retrying later")
            return

        self._finish_cue(current, direction, note, started, ends)

    def _land_cue(
        self,
        current: dict[str, Any],
        state: Any,
        direction: str,
        note: str,
        phase: str,
        steering: str,
    ) -> None:
        runtime = RuntimeController(self.controller.session_store)
        if not runtime.status()["running"]:
            self._defer(current, "Runtime stopped — conductor is holding")
            return
        target_slot = (int(current.get("cue_index", 0)) + 1) % 6
        latest = self.controller.session_store.load(create=False)
        prompt = latest.stream.prompts[target_slot]
        prompt.text = direction
        prompt.weight = 0
        self.controller.session_store.save(latest)
        SuperColliderMixer().stream_prompt(target_slot, direction, 0)
        try:
            prepared = DeckKeeper(self.controller.session_store).prepare(
                direction=direction, duration=64, bpm=state.transport.bpm
            )
        except Exception as exc:  # noqa: BLE001 — generation failure must preserve audio
            self.controller.session_store.events().append(
                "set_cue_failed", error=str(exc), audio_unchanged=True
            )
            self._defer(current, "Preparation failed — retrying later")
            return
        if not prepared.get("ok"):
            self._defer(current, "Prepared audio was rejected — retrying later")
            return

        # Hold/end can arrive while local generation is busy. Recheck before any audible move.
        latest_set = self.store.load()
        if self.stopping or latest_set.get("status") != "running":
            self.controller.session_store.events().append(
                "set_cue_cancelled", reason="conductor held or ended", audio_unchanged=True
            )
            return
        target = prepared["prepared_deck"]
        duration = Transport(state.transport.bpm).bars_to_seconds(8)
        mixer = SuperColliderMixer()
        mixer.crossfade(target, duration)
        latest = self.controller.session_store.load(create=False)
        for name, deck in latest.decks.items():
            deck.status = DeckStatus.PLAYING if name.value == str(target) else DeckStatus.PREPARED
        self.controller.session_store.save(latest)
        if latest.stream.enabled and not latest.stream.force_fallback:
            for item in latest.stream.prompts:
                weight = 1.0 if item.slot == target_slot else 0.0
                mixer.stream_weight(item.slot, weight, duration)
                item.weight = weight
            self.controller.session_store.save(latest)
        self.controller.session_store.events().append(
            "set_cue_landed",
            phase=phase,
            direction=direction,
            to=target,
            transition_bars=8,
            steering=steering or None,
        )

        started = parse_time(current.get("started_at")) or utc_now()
        ends = parse_time(current.get("ends_at")) or (started + timedelta(minutes=90))
        self._finish_cue(current, direction, note, started, ends)

    def _finish_cue(
        self,
        current: dict[str, Any],
        direction: str,
        note: str,
        started: datetime,
        ends: datetime,
    ) -> None:
        current = self.store.load()
        current["cue_index"] = int(current.get("cue_index", 0)) + 1
        current["current_direction"] = direction
        current["current_note"] = note
        current["activity"] = "ready"
        cadence = min(8, max(2, int(current["duration_minutes"]) / 10))
        next_at = min(ends, utc_now() + timedelta(minutes=cadence))
        next_progress = min(
            1.0, (next_at - started).total_seconds() / max(1, (ends - started).total_seconds())
        )
        next_phase, next_phase_direction = phase_for(next_progress)
        current["next_cue_at"] = iso(next_at)
        current["next_direction"] = translate_direction(
            current["brief"], next_phase, next_phase_direction
        )
        current["next_note"] = describe_direction(next_phase, next_phase_direction)
        self.store.save(current)

    def _defer(self, current: dict[str, Any], note: str) -> None:
        latest = self.store.load()
        if latest.get("status") != "running":
            return
        latest["activity"] = "retrying"
        latest["next_note"] = note
        latest["next_cue_at"] = iso(utc_now() + timedelta(minutes=2))
        self.store.save(latest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    if args.run:
        SetWorker(test_mode=args.test_mode).run()


if __name__ == "__main__":
    main()
