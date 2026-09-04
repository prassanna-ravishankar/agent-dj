from __future__ import annotations

import argparse
import asyncio
import os
import signal
import time
from datetime import UTC, datetime

from dj.config import settings
from dj.generator.fake import FakeGenerator
from dj.generator.magenta_live import MagentaLiveGenerator
from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckStatus
from dj.observations import Observation, ObservationStore
from dj.policy import Decision, LocalDJPolicy
from dj.runtime import RuntimeController
from dj.scheduler import ScheduleStore, current_bar
from dj.session import SessionStore
from dj.transport import Transport


class AgentWorker:
    def __init__(self, test_mode: bool = False) -> None:
        self.test_mode = test_mode
        self.running = True
        self.store = SessionStore()
        self.policy = LocalDJPolicy()
        self.generator = None if test_mode else MagentaLiveGenerator()

    def stop(self, *_args: object) -> None:
        self.running = False

    def run(self) -> None:
        settings.sessions_dir.mkdir(parents=True, exist_ok=True)
        (settings.sessions_dir / ".agent-pid").write_text(str(os.getpid()), encoding="utf-8")
        (settings.sessions_dir / ".agent-ready").write_text("ready\n", encoding="utf-8")
        try:
            while self.running:
                try:
                    self.tick()
                except (AssertionError, KeyError, OSError, RuntimeError, ValueError) as exc:
                    try:
                        self.store.events().append("error", subsystem="agent", error=str(exc))
                    except (FileNotFoundError, OSError):
                        print(f"agent error: {exc}", flush=True)
                time.sleep(0.2)
        finally:
            (settings.sessions_dir / ".agent-ready").unlink(missing_ok=True)
            (settings.sessions_dir / ".agent-pid").unlink(missing_ok=True)

    def tick(self) -> None:
        state = self.store.load(create=False)
        events = self.store.events().read()
        processed = {
            event["observation_id"] for event in events
            if event["type"] == "observation_processed"
        }
        observations = ObservationStore(
            self.store.root / state.session_id / "observations.jsonl"
        ).read()
        for observation in observations:
            if observation.id not in processed:
                self.process_observation(observation)
                return
        self.execute_due_schedules()

    def process_observation(self, observation: Observation) -> None:
        state = self.store.load(create=False)
        events = self.store.events()
        if state.future.estimated_seconds < settings.coverage.critical_seconds:
            events.append(
                "warning", kind="future_coverage_critical",
                estimated_seconds=state.future.estimated_seconds,
            )
            if not any(deck.audio_path for deck in state.decks.values()) and not self.test_mode:
                raise RuntimeError("cannot make creative change without a safe playing buffer")
        decision = self.policy.decide(observation, state)
        decision_payload = decision.model_dump(mode="json")
        decision_record = {
            "ts": datetime.now(UTC).isoformat(),
            "type": "agent_decision",
            "goal": decision.goal,
            "evidence": decision.evidence,
            "actions": [
                f"generate deck {decision.target_deck.value}",
                "schedule phrase-aligned transition",
            ],
            "observation_id": observation.id,
            "decision": decision_payload,
        }
        self.store.append_decision(state.session_id, decision_record)
        events.append("agent_decision", **decision_record)
        self.prepare_response(decision)
        state = self.store.load(create=False)
        if not any(item.get("id") == observation.id for item in state.observations):
            state.observations.append(observation.model_dump(mode="json"))
            state.observations = state.observations[-100:]
            self.store.save(state)
        events.append("observation_processed", observation_id=observation.id)

    def prepare_response(self, decision: Decision) -> None:
        state = self.store.load(create=False)
        deck = state.decks[decision.target_deck]
        deck.status = DeckStatus.PREPARING
        self.store.save(state)
        events = self.store.events()
        events.append(
            "generation_requested", deck=decision.target_deck,
            prompt=decision.prompt, source="agent_decision",
            observation_id=decision.observation_id,
        )
        output = (
            self.store.root / state.session_id / "generated" /
            f"reaction-{decision.target_deck.value}-{datetime.now(UTC).strftime('%H%M%S')}.wav"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        if self.test_mode:
            frequencies = {
                "love": 660.0, "dislike": 550.0, "more-energy": 990.0,
                "less-energy": 330.0, "boring": 770.0, "weird": 1230.0,
            }
            kind = decision.evidence[0].split(":", 1)[1]
            generator = FakeGenerator(frequencies[kind])
            asyncio.run(generator.prepare(decision.prompt, state.transport.bpm))
            asyncio.run(generator.start())
            asyncio.run(generator.render(output, 4.0))
            asyncio.run(generator.stop())
            backend = "fake-reaction"
            realtime_factor = 0.0
        else:
            assert self.generator is not None

            async def generate() -> dict[str, object]:
                await self.generator.prepare(decision.prompt, state.transport.bpm)
                await self.generator.start()
                await self.generator.render(output, 16.0)
                return await self.generator.health()

            health = asyncio.run(generate())
            backend = str(health["backend"])
            realtime_factor = float(health["realtime_factor"])
        if RuntimeController().status()["running"]:
            SuperColliderMixer().load(decision.target_deck, output)
        state = self.store.load(create=False)
        target = state.decks[decision.target_deck]
        target.status = DeckStatus.PREPARED
        target.source = "fake" if self.test_mode else "magenta"
        target.prompt = decision.prompt
        target.audio_path = str(output)
        target.duration_seconds = 4.0 if self.test_mode else 16.0
        target.energy = min(1.0, max(0.0, (target.energy or 0.5) + decision.energy_delta))
        state.future.estimated_seconds = 86_400
        transport = Transport(state.transport.bpm)
        now_bar = current_bar(state)
        at_bar = int(now_bar) if self.test_mode else transport.next_phrase_bar(now_bar, 4)
        bars = 0.1 if self.test_mode else decision.transition_bars
        schedule = ScheduleStore(
            self.store.root / state.session_id / "schedules.jsonl"
        ).append(
            "crossfade",
            decision.target_deck.value,
            at_bar,
            bars=bars,
            observation_id=decision.observation_id,
        )
        state.future.covered_until_bar = max(state.future.covered_until_bar, at_bar + round(bars))
        self.store.save(state)
        events.append(
            "generation_ready", deck=decision.target_deck, path=str(output),
            backend=backend, realtime_factor=realtime_factor,
            observation_id=decision.observation_id,
        )
        events.append("transition_scheduled", **schedule)
        self.execute_due_schedules()

    def execute_due_schedules(self) -> None:
        state = self.store.load(create=False)
        schedules = ScheduleStore(
            self.store.root / state.session_id / "schedules.jsonl"
        ).read()
        events = self.store.events()
        executed = {
            event["schedule_id"] for event in events.read()
            if event["type"] == "schedule_executed"
        }
        now_bar = current_bar(state)
        for item in schedules:
            if item["id"] in executed or item["at_bar"] > now_bar:
                continue
            if item["action"] == "crossfade":
                target = state.decks[item["target"]].name
                bars = float(item["parameters"].get("bars", 4))
                seconds = Transport(state.transport.bpm).bars_to_seconds(bars)
                if RuntimeController().status()["running"]:
                    SuperColliderMixer().crossfade(target, seconds)
                for name, deck in state.decks.items():
                    deck.status = DeckStatus.PLAYING if name == target else DeckStatus.PREPARED
                self.store.save(state)
                events.append(
                    "transition_started", to=target, duration_bars=bars,
                    duration_seconds=seconds, observation_driven=True,
                    observation_id=item["parameters"].get("observation_id"),
                )
            elif item["action"] == "stream-weight":
                slot = int(item["target"])
                weight = float(item["parameters"]["weight"])
                bars = float(item["parameters"].get("bars", 8))
                seconds = Transport(state.transport.bpm).bars_to_seconds(bars)
                previous = state.stream.prompts[slot].weight
                state.stream.prompts[slot].weight = weight
                self.store.save(state)
                if RuntimeController().status()["running"]:
                    SuperColliderMixer().stream_weight(slot, weight, seconds)
                events.append(
                    "stream_weight_morphed", slot=slot, from_weight=previous,
                    to_weight=weight, duration_bars=bars,
                    duration_seconds=seconds, scheduled=True,
                )
            events.append(
                "schedule_executed",
                schedule_id=item["id"],
                action=item["action"],
                observation_id=item["parameters"].get("observation_id"),
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    worker = AgentWorker(test_mode=args.test_mode)
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
