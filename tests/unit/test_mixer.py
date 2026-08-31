from unittest.mock import Mock

import pytest

from dj.mixer.supercollider import SuperColliderMixer
from dj.models import DeckName


def test_mixer_translates_db_and_deck_to_explicit_osc_contract() -> None:
    mixer = SuperColliderMixer()
    mixer.client = Mock()
    mixer.set_gain(DeckName.A, -6)
    address, args = mixer.client.send_message.call_args.args
    assert address == "/agent-dj/set"
    assert args[0] == "gainA"
    assert args[1] == pytest.approx(0.501187, rel=1e-5)


def test_mixer_rejects_invalid_filter() -> None:
    with pytest.raises(ValueError):
        SuperColliderMixer().set_filter(DeckName.A, "magic", 1000)

