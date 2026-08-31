# Agent DJ

Agent DJ is a functioning local-first generative music system. Magenta RealTime 2 creates musical
material, SuperCollider keeps audio running and performs real-time mixing, and a separate local
agent turns generic observations into scheduled future musical changes.

The central safety rule is simple: **music must not stop**. Slow generation, policy, analysis, and
file work never run in the real-time audio callback. A safe deck loops if the control process or
agent disappears.

## Architecture

```text
human feedback ─┐
future mic ──────┼─> Observation JSONL ─> local policy ─> generate + schedule
future camera ───┘                                  │
                                                   OSC
Magenta RT 2 ─> prepared stereo buffers ─> SuperCollider decks/mixer ─> audio
```

Magenta can produce audio directly, but the current system keeps SuperCollider as the independent
audio-device, deck, DSP, crossfade, limiter, and recording runtime. The live Magenta adapter is
currently prebuffered: local MLX inference runs faster than playback and replaces safe looping
buffers. Its generic adapter boundary is ready for a future native MRT2 `RealtimeRunner` bridge.

## Setup

Requirements are Python 3.12, `uv`, SuperCollider, and the local MRT2 model assets under `models/`.

```bash
uv sync --extra dev --extra magenta
uv run dj doctor --json
uv run pytest
```

Network access is needed only for initial dependency/model installation. Performance-time
inference, state, observations, policy, audio, and analysis are local.

## Run it

For a deterministic first rehearsal:

```bash
uv run dj session-new --id rehearsal
uv run dj start --test-mode --json
uv run dj agent start --test-mode --json
uv run dj feedback more-energy --json
uv run dj state --json
uv run dj agent stop --json
uv run dj stop --json
```

For Magenta material, prepare both decks locally before starting the runtime:

```bash
uv run dj session-new --id local-magenta
uv run dj generate A --prompt "warm groovy house" --duration 16 --json
uv run dj generate B --prompt "dark hypnotic rolling house" --duration 16 --json
uv run dj start --json
uv run dj play A --json
```

Manual inputs all enter through the same source-neutral boundary:

```bash
uv run dj feedback love --json
uv run dj feedback dislike --json
uv run dj feedback more-energy --json
uv run dj feedback less-energy --json
uv run dj feedback boring --json
uv run dj feedback weird --json
```

## Machine-verifiable acceptance

```bash
uv run dj verify environment --json
uv run dj verify mixer --json
uv run dj verify timing --json
uv run dj verify continuity --minutes 2 --json
uv run dj verify generator --backend magenta-offline --json
uv run dj verify generator --backend magenta-live --json
uv run dj verify dual-deck --minutes 5 --json
uv run dj verify scripted-set --json
uv run dj verify feedback --json
uv run dj verify session latest --json
```

The verifiers inspect recorded audio numerically; they do not ask a person whether a transition
seemed to work. Session artifacts and append-only operational events are stored under `sessions/`.
