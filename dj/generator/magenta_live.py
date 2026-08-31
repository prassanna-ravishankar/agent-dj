from __future__ import annotations

from dj.generator.magenta_offline import MagentaOfflineGenerator


class MagentaLiveGenerator(MagentaOfflineGenerator):
    """Pre-buffered MRT2 live adapter.

    The model generates faster than playback while SuperCollider loops the current safe buffer.
    A future native RealtimeRunner bridge can replace this class behind the same interface.
    """

    async def health(self) -> dict[str, object]:
        report = await super().health()
        report.update(
            {
                "backend": "magenta-mlx-prebuffered-live",
                "mode": "prebuffered",
                "continuous_audio_owner": "supercollider",
            }
        )
        return report

