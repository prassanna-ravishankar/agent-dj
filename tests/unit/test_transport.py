from dj.transport import Transport


def test_phrase_and_bar_math() -> None:
    transport = Transport(bpm=120)
    assert transport.seconds_per_bar == 2
    assert transport.bars_to_seconds(16) == 32
    assert transport.next_phrase_bar(1, 16) == 16
    assert transport.next_phrase_bar(16, 16) == 32

