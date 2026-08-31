from __future__ import annotations

from pydantic import BaseModel

from dj.models import DeckName, DeckStatus, DJState
from dj.observations import FeedbackKind, Observation


class Decision(BaseModel):
    observation_id: str
    goal: str
    evidence: list[str]
    target_deck: DeckName
    prompt: str
    transition_bars: float
    energy_delta: float


class LocalDJPolicy:
    """Deterministic local policy that interprets observations as musical intent."""

    def decide(self, observation: Observation, state: DJState) -> Decision:
        try:
            kind = FeedbackKind(observation.kind)
        except ValueError as exc:
            raise ValueError(f"unsupported observation kind: {observation.kind}") from exc
        playing = next(
            (name for name, deck in state.decks.items() if deck.status is DeckStatus.PLAYING),
            DeckName.A,
        )
        target = DeckName.B if playing == DeckName.A else DeckName.A
        base = state.decks[playing].prompt or "groovy instrumental house"
        policies = {
            FeedbackKind.LOVE: (
                "reinforce what is working without a sharp change",
                f"{base}, preserve the groove, subtle evolution, patient arrangement",
                8.0,
                0.05,
            ),
            FeedbackKind.DISLIKE: (
                "move to a coherent alternative direction",
                "warm rolling instrumental house, grounded groove, restrained melody",
                4.0,
                -0.05,
            ),
            FeedbackKind.MORE_ENERGY: (
                "increase energy through density and drive",
                f"{base}, more driving, denser percussion, stronger bass movement, instrumental",
                4.0,
                0.2,
            ),
            FeedbackKind.LESS_ENERGY: (
                "release energy while preserving continuity",
                f"{base}, spacious, restrained percussion, lower intensity, warm instrumental",
                8.0,
                -0.2,
            ),
            FeedbackKind.BORING: (
                "introduce novelty without abandoning the set",
                f"{base}, surprising rhythmic variation, fresh hook, coherent instrumental",
                4.0,
                0.1,
            ),
            FeedbackKind.WEIRD: (
                "take a controlled unexpected detour",
                f"{base}, playful psychedelic textures, unusual percussion, still danceable",
                4.0,
                0.05,
            ),
        }
        goal, prompt, bars, delta = policies[kind]
        return Decision(
            observation_id=observation.id,
            goal=goal,
            evidence=[
                f"{observation.source}:{observation.kind}",
                f"confidence={observation.confidence:.2f}",
                f"current_deck={playing.value}",
            ],
            target_deck=target,
            prompt=prompt,
            transition_bars=bars,
            energy_delta=delta,
        )
