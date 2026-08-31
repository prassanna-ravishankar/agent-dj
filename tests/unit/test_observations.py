from dj.observations import FeedbackKind, ObservationStore, manual_feedback


def test_manual_feedback_uses_generic_observation_contract() -> None:
    observation = manual_feedback(FeedbackKind.MORE_ENERGY)
    assert observation.source == "human"
    assert observation.kind == "more-energy"
    assert observation.confidence == 1.0


def test_observation_store_round_trip_is_source_neutral(tmp_path) -> None:
    store = ObservationStore(tmp_path / "observations.jsonl")
    human = manual_feedback(FeedbackKind.WEIRD)
    camera = human.model_copy(
        update={"source": "camera", "kind": "motion_energy", "value": 0.7}
    )

    store.append(human)
    store.append(camera)

    assert store.read() == [human, camera]
