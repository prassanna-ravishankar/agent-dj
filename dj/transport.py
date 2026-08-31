from __future__ import annotations

import math


class Transport:
    def __init__(self, bpm: float = 124.0, beats_per_bar: int = 4) -> None:
        if bpm <= 0:
            raise ValueError("bpm must be positive")
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    @property
    def seconds_per_bar(self) -> float:
        return self.seconds_per_beat * self.beats_per_bar

    def bars_to_seconds(self, bars: float) -> float:
        return bars * self.seconds_per_bar

    def next_phrase_bar(self, current_bar: float, phrase_bars: int = 16) -> int:
        if phrase_bars <= 0:
            raise ValueError("phrase_bars must be positive")
        return math.ceil((current_bar + 1e-9) / phrase_bars) * phrase_bars

