from __future__ import annotations

import pytest

from dj.models import DeckName, DeckStatus, DJState
from dj.observations import FeedbackKind, Observation, manual_feedback
from dj.policy import LocalDJPolicy


@pytest.mark.parametrize("kind", list(FeedbackKind))
def test_every_manual_feedback_kind_becomes_a_future_musical_decision(
    kind: FeedbackKind,
) -> None:
    state = DJState(session_id="policy-test")
    state.decks[DeckName.A].status = DeckStatus.PLAYING
    state.decks[DeckName.A].prompt = "warm house"

    decision = LocalDJPolicy().decide(manual_feedback(kind), state)

    assert decision.target_deck is DeckName.B
    assert decision.prompt
    assert decision.transition_bars > 0
    assert decision.evidence[0] == f"human:{kind.value}"


def test_policy_rejects_unknown_observation_without_mutating_state() -> None:
    state = DJState(session_id="policy-test")
    before = state.model_dump_json()

    with pytest.raises(ValueError, match="unsupported observation kind"):
        LocalDJPolicy().decide(
            Observation(source="camera", kind="unmapped-motion", value=0.8), state
        )

    assert state.model_dump_json() == before
