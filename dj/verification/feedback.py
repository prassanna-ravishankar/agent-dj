from __future__ import annotations

import asyncio
import gc
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dj.agent import AgentController
from dj.generator.magenta_live import MagentaLiveGenerator
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckName, DeckStatus
from dj.observations import FeedbackKind, ObservationStore, manual_feedback
from dj.runtime import RuntimeController
from dj.session import SessionStore
from dj.verification.audio import longest_silence, tone_magnitude


def _restore_current(store: SessionStore, previous: str | None) -> None:
    if previous is None:
        store.current_file.unlink(missing_ok=True)
    else:
        store.current_file.write_text(previous, encoding="utf-8")


def _wait_for_event(
    store: SessionStore,
    event_type: str,
    observation_id: str,
    timeout: float = 15.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(
            event["type"] == event_type and event.get("observation_id") == observation_id
            for event in store.events().read()
        ):
            return True
        time.sleep(0.1)
    return False


def _analyse_reaction(path: Path, test_mode: bool) -> dict[str, Any]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    mono = audio.mean(axis=1)
    duration = len(mono) / sample_rate
    before_end = 0.55 if test_mode else min(2.5, duration / 3)
    after_length = 0.7 if test_mode else min(2.5, duration / 3)
    before = mono[int(0.15 * sample_rate) : int(before_end * sample_rate)]
    after = mono[int(max(0, duration - after_length) * sample_rate) :]
    before_440 = tone_magnitude(before, sample_rate, 440)
    before_990 = tone_magnitude(before, sample_rate, 990)
    after_440 = tone_magnitude(after, sample_rate, 440)
    after_990 = tone_magnitude(after, sample_rate, 990)
    result = {
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "channels": audio.shape[1],
        "longest_silence_ms": longest_silence(audio, sample_rate),
        "before_440_to_990": before_440 / max(before_990, 1e-9),
        "after_990_to_440": after_990 / max(after_440, 1e-9),
    }
    if not test_mode:
        frames = min(len(before), len(after))
        before_spectrum = np.abs(np.fft.rfft(before[:frames] * np.hanning(frames)))
        after_spectrum = np.abs(np.fft.rfft(after[-frames:] * np.hanning(frames)))
        similarity = float(
            np.dot(before_spectrum, after_spectrum)
            / max(np.linalg.norm(before_spectrum) * np.linalg.norm(after_spectrum), 1e-9)
        )
        result["before_after_spectral_similarity"] = similarity
    return result


def verify_feedback_reaction(backend: str = "fake") -> dict[str, Any]:
    """Prove observation -> decision -> generation -> schedule -> audible response."""
    if backend not in {"fake", "magenta-live"}:
        return {"ok": False, "error": f"unsupported feedback backend: {backend}"}
    test_mode = backend == "fake"
    store = SessionStore()
    runtime = RuntimeController(store)
    agent = AgentController()
    if runtime.status()["running"] or agent.status()["running"]:
        return {
            "ok": False,
            "error": "verification refuses to disturb an active audio runtime or agent",
        }
    previous = store.current_id()
    session_id = f"verify-feedback-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    render = store.root / session_id / "renders" / f"feedback-{backend}.wav"
    started_runtime = False
    started_agent = False
    try:
        state = store.create(session_id)
        generator_health: dict[str, Any] | None = None
        if not test_mode:
            initial = store.root / session_id / "generated" / "initial-a.wav"
            generator = MagentaLiveGenerator()

            async def generate_initial() -> dict[str, Any]:
                await generator.prepare("warm groovy instrumental house", state.transport.bpm)
                await generator.start()
                await generator.render(initial, 8.0)
                health = await generator.health()
                await generator.stop()
                return health

            generator_health = asyncio.run(generate_initial())
            state.decks[DeckName.A].audio_path = str(initial)
            state.decks[DeckName.A].duration_seconds = 8.0
            state.decks[DeckName.A].source = "magenta"
            state.decks[DeckName.A].prompt = "warm groovy instrumental house"
            state.decks[DeckName.A].status = DeckStatus.PREPARED
            store.save(state)
            del generator
            gc.collect()
        runtime.start(test_mode=test_mode)
        started_runtime = True
        time.sleep(0.5)
        agent.start(test_mode=test_mode)
        started_agent = True
        SuperColliderMixer().record("start", render)
        time.sleep(0.5)

        observation = manual_feedback(FeedbackKind.MORE_ENERGY)
        store.events().append(
            "observation_received",
            observation_id=observation.id,
            observation=observation.model_dump(mode="json"),
        )
        ObservationStore(store.root / session_id / "observations.jsonl").append(observation)

        completed = _wait_for_event(
            store,
            "observation_processed",
            observation.id,
            timeout=20.0 if test_mode else 60.0,
        )
        transitioned = _wait_for_event(
            store,
            "schedule_executed",
            observation.id,
            timeout=5.0 if test_mode else 20.0,
        )
        time.sleep(1.0 if test_mode else 9.0)
        SuperColliderMixer().record("stop")
        time.sleep(0.5)
        events = store.events().read()
        if not render.exists():
            return {"ok": False, "error": "master recording was not created", "events": events}
        measurements = _analyse_reaction(render, test_mode)
        event_types = [event["type"] for event in events]
        required = [
            "observation_received",
            "agent_decision",
            "generation_ready",
            "transition_scheduled",
            "transition_started",
            "schedule_executed",
            "observation_processed",
        ]
        positions = [event_types.index(name) if name in event_types else -1 for name in required]
        ordered = (
            all(position >= 0 for position in positions)
            and positions[0] < positions[1] < positions[2] < positions[3]
            and positions[3] < positions[4] < positions[5]
            and positions[3] < positions[6]
        )
        checks = {
            "observation_is_source_neutral": set(observation.model_fields) >= {
                "source", "kind", "value", "confidence", "timestamp", "metadata"
            },
            "agent_completed": completed,
            "event_chain_complete": all(position >= 0 for position in positions),
            "event_chain_ordered": ordered,
            "transition_executed": transitioned,
            "audible_material_changed": (
                measurements["before_440_to_990"] > 20
                and measurements["after_990_to_440"] > 20
                if test_mode
                else measurements["before_after_spectral_similarity"] < 0.98
            ),
            "music_did_not_stop": measurements["longest_silence_ms"] < 100,
            "runtime_survived": runtime.status()["running"],
        }
        return {
            "ok": all(checks.values()),
            "session_id": session_id,
            "observation_id": observation.id,
            "input": FeedbackKind.MORE_ENERGY.value,
            "backend": backend,
            "expected_reaction_hz": 990 if test_mode else None,
            "initial_generator": generator_health,
            "render": str(render),
            "checks": checks,
            "measurements": measurements,
            "event_chain": required,
        }
    finally:
        if started_agent:
            agent.stop()
        if started_runtime:
            runtime.stop()
        _restore_current(store, previous)
