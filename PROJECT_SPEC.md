# Agent DJ

## Project Specification

**Status:** Initial architecture / build specification  
**Working repository name:** `agent-dj`  
**Primary environment:** macOS / Apple Silicon  
**Primary operator:** Codex or Claude Code  
**Primary design goal:** an autonomous live DJ assembled from composable existing tools

---

# 1. Vision

Agent DJ is a local-first autonomous live electronic-music performer.

It does not generate a playlist.

It does not merely generate finished songs.

It does not implement a DAW.

It composes existing music-generation, audio-analysis and real-time DSP systems behind a small set of stable tools that an external coding agent can operate.

The long-term system should be capable of:

1. generating continuous musical material;
2. running multiple musical sources/decks simultaneously;
3. mixing, filtering and transitioning between them;
4. reasoning about the musical trajectory of an entire set;
5. observing audience feedback;
6. adapting subsequent musical decisions;
7. eventually observing a physical room through microphones and cameras;
8. performing for long periods without requiring a human operator.

The desired eventual interaction is:

```bash
dj start \
  "Play for 90 minutes.

   Begin with groovy warm house around 124 BPM.
   Slowly become darker and more hypnotic.
   Don't rush.
   Long transitions.
   Sparse vocals.
   Peak around an hour in.
   Do something unexpected once you have the room."
```

From that point onward, the system performs.

---

# 2. Core Philosophy

The project is primarily an **orchestration problem**.

Whenever an existing tool already performs some musical or signal-processing operation adequately, wrap that tool rather than reimplementing it.

Examples:

```text
music generation       → Magenta RealTime 2
real-time audio/DSP    → SuperCollider initially
beat/BPM analysis      → Essentia
loudness analysis      → Essentia
key estimation         → Essentia
agent reasoning        → Codex / Claude Code
camera primitives      → OpenCV / existing models
audio I/O              → existing audio runtime
```

Agent DJ itself should primarily implement:

```text
state
tool interfaces
musical scheduling
observations
agent-readable context
verification
failure isolation
set history
```

The fundamental question for every new feature is:

> Is this intelligence unique to the DJ, or can another tool already perform it?

If another tool can perform it, integrate that tool.

---

# 3. Technical Baseline

## 3.1 Music generation

Primary generator:

**Magenta RealTime 2**

Initial model:

```text
mrt2_small
```

Use `mrt2_small` initially because development should optimize for reliable real-time operation rather than maximum generation quality.

MRT2 currently provides:

- Python inference via MLX/JAX;
- C++ inference through `magentart::core`;
- `RealtimeRunner` for streaming generation;
- prompt conditioning;
- audio conditioning;
- an official SuperCollider integration;
- standalone and plugin examples.

The Python package is useful for:

- initial capability checks;
- offline renders;
- evaluation;
- prompt experiments;
- CI-like local tests.

The C++ `RealtimeRunner` should eventually be preferred for hardened live streaming.

---

# 4. Magenta Adapter Strategy

Generation must live behind:

```python
class Generator:
    async def prepare(...)
    async def start(...)
    async def update_conditioning(...)
    async def stop(...)
    async def health(...)
```

Implement at least three generator implementations.

## 4.1 `FakeGenerator`

Deterministic synthetic audio.

Examples:

- Deck A = 440 Hz sine
- Deck B = 880 Hz sine
- optional click track
- optional pink noise
- optional fixed WAV fixture

This backend exists exclusively for automated verification.

It is extremely important.

Most tests must **not depend on generative music behaving deterministically**.

---

## 4.2 `MagentaOfflineGenerator`

Uses the Python `magenta-rt` package.

Produces chunks/files.

Purpose:

- prove installation works;
- prompt experiments;
- evaluate output;
- fallback pre-buffering;
- test MusicCoCa embeddings;
- verify model resources.

This is not the target live architecture.

---

## 4.3 `MagentaLiveGenerator`

Provides actual continuous streaming.

Two implementations may exist.

### Development implementation

Use the upstream SuperCollider MagentaRT UGen if available.

Call this:

```text
MagentaSCGenerator
```

Treat it as an optional adapter.

Do not vendor or modify the upstream SC plugin.

### Hardened implementation

Use:

```text
magentart::core
RealtimeRunner
```

behind a dedicated native bridge.

Call this:

```text
MagentaCoreGenerator
```

This becomes the preferred long-term backend.

The rest of Agent DJ must not know which one is running.

---

# 5. Real-Time System Boundary

This is the most important architectural boundary.

## Real-time audio code

May:

- read audio buffers;
- apply DSP;
- update already-allocated parameters;
- move samples through buses;
- execute previously scheduled operations.

Must not:

- invoke an LLM;
- invoke Python callbacks;
- access the network;
- allocate arbitrary memory;
- install dependencies;
- read configuration files;
- wait on subprocesses;
- generate JSON;
- write logs synchronously;
- perform expensive analysis.

---

## Agent code

May:

- reason slowly;
- inspect state;
- generate prompts;
- schedule future operations;
- ask for analysis;
- change set direction;
- prepare musical material;
- respond to observations.

It may take seconds.

That must not matter to the audio runtime.

---

# 6. Two Clocks

The system has two fundamentally different clocks.

## Audio clock

Timescale:

```text
samples → milliseconds
```

Responsibilities:

- audio output;
- DSP;
- buffer movement;
- fades;
- parameter smoothing;
- transport;
- exact scheduled events.

No agent dependency.

---

## Musical/agent clock

Timescale:

```text
bars → phrases → minutes
```

Responsibilities:

- musical intent;
- energy trajectory;
- generation prompts;
- deciding when to transition;
- reacting to crowd feedback;
- planning the set.

Latency of several seconds is acceptable.

---

# 7. Audio Runtime

Initial runtime:

**SuperCollider**

SuperCollider should own:

- audio devices;
- audio buses;
- deck buses;
- master bus;
- gain;
- EQ;
- filters;
- crossfade;
- effects;
- recording;
- master limiter;
- transport-aligned automation.

The Python process controls it through OSC.

Avoid putting Python in the audio path.

---

# 8. SuperCollider Topology

Initial graph:

```text
               Generator A
                    │
                    ▼
             ┌─────────────┐
             │ Deck A Bus  │
             └──────┬──────┘
                    │
                 Deck DSP
                    │
                    ├─────────────┐
                    │             │
                    │          crossfade
                    │             │
                    ▼             ▼
               MASTER MIX BUS ◄────
                    ▲
                    │
                    │
                 Deck DSP
                    │
             ┌──────┴──────┐
             │ Deck B Bus  │
             └─────────────┘
                    ▲
                    │
               Generator B

                       │
                       ▼
                    Limiter
                       │
                       ▼
                  OUTPUT BUS

                       │
                       └──→ recorder
```

Effects should operate on buses.

Initial DSP:

- gain
- high-pass filter
- low-pass filter
- 3-band EQ if practical
- delay
- reverb
- master limiter

Do not build a plugin framework.

---

# 9. OSC Boundary

Python must communicate with SuperCollider through a small explicit OSC adapter.

Prefer standard server operations where practical.

Examples:

```text
/n_set
/s_new
/n_free
/s_get
/sync
/status
```

Do not scatter OSC addresses throughout application code.

Create:

```python
class MixerBackend:
    def set_gain(...)
    def set_filter(...)
    def crossfade(...)
    def schedule(...)
    def status(...)
```

The SuperCollider implementation owns OSC details.

---

# 10. Transport

Agent DJ needs a global musical transport.

Canonical transport state:

```json
{
  "playing": true,
  "bpm": 126.0,
  "bar": 184,
  "beat": 3.25,
  "started_at": "...",
  "sample_position": 48720934
}
```

Agent-facing scheduling should operate primarily in:

```text
beats
bars
phrases
```

not wall-clock seconds.

Examples:

```bash
dj transition A B --at next-phrase --bars 32
```

```bash
dj filter A lowpass 1800 --over-bars 8
```

```bash
dj gain B -3 --at bar+16
```

Internally these become deterministic runtime events.

---

# 11. Phrase Model

Default phrase assumptions for electronic music:

```text
4 beats / bar
8 bars
16 bars
32 bars
64 bars
```

Do not pretend this is universally correct.

The transport must support arbitrary signatures later.

For v0:

```text
4/4 only
```

is acceptable.

---

# 12. Control Plane

Language:

```text
Python 3.12
```

Primary responsibilities:

- CLI
- state model
- process supervision
- generator adapters
- SuperCollider adapter
- event log
- session storage
- verification
- observations
- scheduling API
- agent-facing descriptions

Suggested libraries:

```text
typer
pydantic
python-osc
rich
numpy
```

Use `uv` for Python environment management.

Avoid adding infrastructure dependencies unless necessary.

---

# 13. Process Model

Run major concerns as separate processes.

```text
dj-runtime
    audio runtime / SuperCollider lifecycle

dj-control
    state + API

dj-generator
    Magenta adapter when separate process is needed

dj-agent
    external Codex / Claude invocation context

dj-perception
    future sensor process
```

The project must tolerate individual process failure where possible.

---

# 14. External Agent Boundary

Do **not** embed OpenAI or Anthropic SDK calls in the core system initially.

Codex or Claude Code is the DJ agent.

It operates the repository exactly like a coding environment.

Its interface to the live system is the CLI.

For example:

```bash
dj state --json

dj generate B \
  --prompt "rolling hypnotic house, restrained acid, sparse melody" \
  --bpm 127

dj crossfade A B \
  --at next-32 \
  --bars 32

dj observe --since 5m

dj analyse master --window 60
```

This creates an intentional separation between:

```text
AGENT
and
DJ SYSTEM
```

Any future agent can operate the same interface.

---

# 15. AGENTS.md Contract

The repository should include an `AGENTS.md`.

It should tell Codex/Claude:

```text
You are operating a live music system.

Your highest-priority invariant is:

MUSIC MUST NOT STOP.

Before making a musical decision:

1. run `dj state --json`;
2. inspect future coverage;
3. if coverage is unsafe, extend it before doing anything creative.

Do not:
- restart the audio runtime during a live session;
- install packages during a live session;
- edit runtime code during a live session;
- use uncertified tools;
- delete active audio buffers;
- schedule destructive operations without a fallback.

You may:
- generate future material;
- modify deck parameters;
- schedule transitions;
- perform analysis;
- respond to observations;
- record decisions.

Prefer doing nothing over making an unnecessary musical change.
```

---

# 16. DJ State

Canonical state example:

```json
{
  "session": {
    "id": "2026-08-31T22-00",
    "status": "live"
  },

  "transport": {
    "bpm": 126,
    "bar": 184,
    "beat": 3.1
  },

  "decks": {
    "A": {
      "state": "playing",
      "source": "magenta",
      "prompt": "groovy warm house",
      "gain_db": -1.5,
      "energy": 0.67
    },

    "B": {
      "state": "prepared",
      "source": "magenta",
      "prompt": "hypnotic darker rolling groove",
      "gain_db": -60,
      "energy": 0.74
    }
  },

  "master": {
    "peak_dbfs": -2.1,
    "lufs_short": -11.4,
    "limiter_reduction_db": 0.3
  },

  "future": {
    "covered_until_bar": 256,
    "estimated_seconds": 137
  },

  "observations": []
}
```

---

# 17. Future Coverage

Define:

```text
future coverage
```

as the amount of time for which the runtime can safely continue producing valid audio without requiring another agent decision.

Target:

```text
normal:        >= 90 seconds
warning:       < 60 seconds
critical:      < 30 seconds
```

These numbers should be configurable.

The runtime should never deliberately stop because future planning ran out.

If no future transition exists:

```text
continue current deck
```

is valid.

---

# 18. Set Intent

A session starts from a structured intent.

Example:

```yaml
duration_minutes: 90

bpm:
  start: 124
  max: 132

styles:
  start:
    - groovy house
    - warm
    - percussion-forward

  middle:
    - rolling house
    - hypnotic

  peak:
    - dark
    - driving
    - restrained acid

  ending:
    - spacious
    - warm

preferences:
  transitions: long
  vocals: sparse
  obvious_drops: avoid
  repetition: welcome
  abrupt_genre_changes: avoid

arc:
  - warm
  - playful
  - build
  - hypnotic
  - peak
  - release

special_instruction:
  "Once the room is committed, take one unexpected detour."
```

---

# 19. DJ Personality

Store long-term aesthetic policy separately from individual set intent.

`SOUL.md`:

```markdown
# DJ Identity

You value groove over novelty.

You are patient.

You like:
- percussion
- hypnotic repetition
- long blends
- bass movement
- slow transformations
- subtle tension
- moments of unexpected euphoria

You dislike:
- cheesy EDM drops
- unnecessary vocals
- changing direction constantly
- obvious build/drop clichés

Do not assume higher BPM means higher energy.

If something works, allow it to work.

A good DJ does not need to demonstrate that they are doing something every minute.
```

---

# 20. Performance Commands

## Runtime

```bash
dj start
dj stop
dj status
dj doctor
```

---

## Decks

```bash
dj deck create A
dj deck create B

dj deck status A
dj deck status B
```

---

## Generation

```bash
dj generate A \
  --prompt "warm groovy house" \
  --bpm 124

dj generate B \
  --prompt "hypnotic rolling house" \
  --bpm 126
```

Potential later controls:

```text
temperature
seed
density
drum mode
audio conditioning
prompt interpolation
```

Do not expose model-specific controls directly through the generic API unless needed.

---

# 21. Prompt Surfaces

The generator interface should eventually support weighted prompt concepts rather than one giant string.

Example:

```yaml
prompts:
  - text: "hypnotic house"
    weight: 0.7

  - text: "rolling percussion"
    weight: 0.6

  - text: "acid bass"
    weight: 0.2
```

This maps naturally onto MRT2's ability to work with prompt conditioning.

The generic project vocabulary should call this:

```text
conditioning
```

rather than Magenta-specific terminology.

---

# 22. Mixer Commands

```bash
dj gain A -4

dj gain A -1 \
  --over-bars 8

dj filter A lowpass 2200

dj filter A lowpass 800 \
  --over-bars 8

dj eq A \
  --low -6 \
  --mid 0 \
  --high 1

dj crossfade A B \
  --bars 32

dj crossfade A B \
  --at next-32 \
  --bars 32
```

---

# 23. Effects

Initial effect vocabulary:

```text
lowpass
highpass
delay
reverb
```

Example:

```bash
dj effect A add delay \
  --mix 0.25 \
  --feedback 0.4

dj effect A remove delay \
  --over-bars 4
```

Do not implement exotic effects until the agent demonstrates a concrete need.

---

# 24. Analysis

Primary analysis library:

**Essentia**

Expose initially:

```text
BPM
beat locations
loudness
peak level
key
scale
onset rate
spectral descriptors
```

Example:

```bash
dj analyse A --window 30 --json
```

```json
{
  "bpm": 125.8,
  "bpm_confidence": 0.88,
  "key": "F#",
  "scale": "minor",
  "integrated_lufs": -11.7,
  "onset_rate": 4.3,
  "spectral_centroid": 1744
}
```

---

# 25. Derived Musical Features

Agent DJ may derive higher-level approximate features.

Examples:

```text
energy
brightness
density
percussiveness
bass_weight
novelty
```

These must be documented as heuristics.

For example:

```text
energy =
  weighted(
    loudness,
    onset_rate,
    spectral_flux,
    bass_energy
  )
```

Do not expose heuristic metrics as objective musical truth.

---

# 26. Event Log

Every meaningful operation generates an append-only event.

Storage:

```text
JSONL
```

initially.

Example:

```json
{
  "ts": "2026-08-31T22:31:02.183Z",
  "type": "transition_started",
  "from": "A",
  "to": "B",
  "bar": 192,
  "duration_bars": 32
}
```

Event classes:

```text
runtime_started
runtime_stopped

generation_requested
generation_started
generation_ready
generation_failed

deck_started
deck_stopped

transition_scheduled
transition_started
transition_finished

parameter_changed
effect_added
effect_removed

observation_received

agent_decision

warning
error

verification_result
```

---

# 27. Agent Decisions

Do not store private reasoning traces.

Record a concise operational explanation.

Example:

```json
{
  "type": "agent_decision",

  "goal": "increase tension without raising BPM",

  "evidence": [
    "movement_feedback rising",
    "current groove positively rated",
    "set is approaching planned peak"
  ],

  "actions": [
    "prepare darker deck B",
    "reduce deck A low frequencies over 16 bars",
    "begin 32 bar transition"
  ]
}
```

This should make post-set debugging possible.

---

# 28. Observations

All feedback enters through one generic abstraction.

```json
{
  "source": "human",
  "kind": "energy_request",
  "value": 0.8,
  "confidence": 1.0,
  "timestamp": "..."
}
```

Sources may eventually include:

```text
human
camera
microphone
phone
wearable
lighting
crowd-vote
venue
```

The DJ should not have special core logic for each sensor.

---

# 29. Manual Feedback

Before any computer vision:

```bash
dj feedback love
dj feedback dislike
dj feedback more-energy
dj feedback less-energy
dj feedback weird
dj feedback boring
```

These must become observations.

They must **not** directly mutate mixer parameters.

Example:

```text
more-energy
```

must not mean:

```text
BPM += 5
```

The agent interprets it.

---

# 30. Webcam Boundary

Webcam support is a later milestone.

Raw video should remain local.

Default behaviour:

```text
raw frames:
    ephemeral

stored:
    false
```

The perception process emits only structured observations.

Initial webcam signals:

```text
people_visible
movement
movement_trend
movement_distribution
room_brightness
```

Avoid attempting:

```text
emotion recognition
identity recognition
demographic classification
```

They are unnecessary to the musical objective.

The important question is:

> Did the room become more or less physically active?

---

# 31. Microphone Boundary

Microphone input should similarly become structured signals.

Possible features:

```text
crowd_loudness
non_music_activity
cheering_like_transient
conversation_level
room_noise
```

The microphone perception system must account for the fact that the DJ's own output dominates the microphone signal.

Possible strategies:

- use known master output as reference;
- estimate residual crowd signal;
- use frequency bands less dominated by the music;
- compare relative changes rather than absolute values.

Do not attempt perfect source separation in the first version.

---

# 32. Development Mode vs Performance Mode

This boundary is important.

## Development mode

Codex/Claude may:

- edit source code;
- install dependencies;
- add new tools;
- restart services;
- run tests;
- rebuild native components.

---

## Performance mode

Codex/Claude may:

- call certified DJ commands;
- generate music;
- schedule events;
- inspect state;
- analyse audio;
- react to observations.

It may **not**:

- edit runtime code;
- install packages;
- rebuild binaries;
- hot-load arbitrary newly written DSP;
- restart the live audio process.

This avoids an agent destroying the performance while attempting to improve its own instrument.

---

# 33. Tool Self-Extension

Long term, the coding agent may write new musical tools.

But never directly into the live runtime.

Workflow:

```text
agent wants capability
        ↓
creates experimental tool
        ↓
static validation
        ↓
unit tests
        ↓
offline audio render
        ↓
automated audio verification
        ↓
integration test
        ↓
tool certification
        ↓
available next session
```

Command:

```bash
dj tool certify tools/experimental/gated_reverb
```

Certified tools receive a manifest.

```yaml
name: gated_reverb
version: 1
status: certified
tests:
  unit: pass
  render: pass
  realtime: pass
```

No human approval is required for technical certification.

Human taste is a different question.

---

# 34. The Verification Principle

The project should be designed so Codex can answer:

> Did I actually build this correctly?

without asking the user to listen every five minutes.

Every milestone requires:

```text
machine-verifiable acceptance criteria
```

The verification system is a first-class feature.

Provide:

```bash
dj verify
```

and subsystem variants:

```bash
dj verify environment
dj verify generator
dj verify audio
dj verify mixer
dj verify transport
dj verify transition
dj verify continuity
dj verify failure
dj verify set
```

Results must be machine-readable:

```bash
dj verify --json
```

---

# 35. `dj doctor`

Codex should begin every development session with:

```bash
dj doctor --json
```

Checks:

```text
OS
architecture
Python version
uv availability

SuperCollider installed
scsynth available
sclang available

Magenta package import
Magenta model assets
model backend
available model sizes

optional Magenta SC UGen

Essentia import

audio output devices
sample rate compatibility

disk space
session paths
permissions
```

Example:

```json
{
  "ok": true,

  "platform": {
    "os": "macOS",
    "arch": "arm64"
  },

  "magenta": {
    "python": true,
    "small_model": true,
    "base_model": false,
    "live_backend": "sc_ugen"
  },

  "supercollider": {
    "server": true,
    "language": true
  },

  "essentia": true,

  "audio": {
    "output": "MacBook Pro Speakers",
    "sample_rate": 48000
  }
}
```

---

# 36. Deterministic Audio Test Mode

Create:

```bash
dj start --test-mode
```

In test mode:

```text
Deck A = 440 Hz
Deck B = 880 Hz
```

This allows automated validation of mixing.

Never depend on generative output for DSP correctness tests.

---

# 37. Mixer Verification

Test:

```text
A only
B only
50/50
crossfade A→B
gain automation
filter automation
```

Record master output to WAV.

Then inspect spectral energy.

For example:

```text
before transition:
440 Hz dominant

midpoint:
440 Hz and 880 Hz both present

after transition:
880 Hz dominant
```

This proves crossfading without listening.

Acceptance:

```text
PASS:
expected frequency dominance observed
transition duration within tolerance
no NaN samples
no unexpected clipping
```

---

# 38. Timing Verification

Synthetic click generator:

```text
one click per beat
accent on bar start
```

Schedule:

```text
crossfade begins bar 32
```

Record output.

Automatically detect the expected parameter/audio change.

Initial tolerance:

```text
<= 50 ms
```

Tighten later if useful.

---

# 39. Continuity Verification

One of the most important tests.

Run:

```bash
dj verify continuity --minutes 5
```

Use deterministic continuous sources.

Inject:

```text
agent pause
generation delay
temporary analysis failure
```

Record master.

Measure:

```text
unexpected zero-output windows
audio callback underruns
buffer underruns
process crashes
```

Acceptance:

```text
unexpected silence > 100 ms: 0
runtime crashes: 0
```

The exact silence threshold may be tuned.

---

# 40. Generator Verification

For MRT2:

```bash
dj verify generator --backend magenta
```

Codex should automatically:

1. load the model;
2. generate known-duration output;
3. save it;
4. inspect the WAV;
5. confirm:
   - correct sample rate;
   - stereo channels;
   - finite samples;
   - non-trivial RMS;
   - no malformed output;
6. calculate generation speed.

Report:

```json
{
  "generated_seconds": 30,
  "wall_seconds": 18.4,
  "realtime_factor": 0.61,
  "realtime_capable": true
}
```

If generation is slower than real-time:

```text
do not fail the entire project
```

Instead classify the backend:

```text
streaming
prebuffered
offline-only
```

---

# 41. Magenta Semantic Proxy

Musical quality cannot be mechanically proven.

However, prompt alignment can have weak automated proxies.

MRT2 provides MusicCoCa text/audio embeddings.

A verification experiment may:

1. generate audio for several distinct prompts;
2. embed generated audio;
3. embed prompt text;
4. compare relative similarity.

Example prompts:

```text
ambient piano
heavy electronic percussion
bright disco funk
dark hypnotic techno
```

Expectation:

```text
audio generated from prompt X should generally be
more similar to X than unrelated prompts
```

This is only a regression signal.

It is not a taste metric.

---

# 42. Analysis Verification

Keep fixture audio with known properties.

For example:

```text
120 BPM click
128 BPM drum loop
440 Hz tone
A minor reference
silence
```

Assert Essentia output is approximately correct.

Example:

```text
fixture: 128 BPM

PASS:
125 <= detected_bpm <= 131
```

Use tolerant ranges.

---

# 43. Crossfade Verification

Test with deterministic sources.

Schedule:

```text
32-bar equal-power A→B
```

Measure windowed RMS or spectral component strengths.

Assert:

```text
A monotonically decreases
B monotonically increases
master does not collapse unexpectedly
transition completes on target bar
```

---

# 44. DSP Verification

For filters:

```text
input:
white noise

apply:
lowpass 1000 Hz
```

Inspect spectrum.

Assert meaningful attenuation above cutoff.

For gain:

```text
input:
known sine amplitude

apply:
-6 dB
```

Assert output approximately:

```text
0.501 × input amplitude
```

This allows Codex to verify audio primitives numerically.

---

# 45. Failure Injection

Build failure testing into the project.

Examples:

```bash
dj chaos agent-pause --seconds 60
dj chaos generator-fail B
dj chaos analysis-crash
dj chaos command-delay --seconds 10
```

These should be available only in development/test mode.

---

# 46. Failure Acceptance Criteria

## Agent disappears

Test:

```text
kill agent/controller client
```

Expected:

```text
audio continues
```

---

## Generator B fails

Expected:

```text
Deck A continues
transition cancelled
warning emitted
```

---

## Analysis dies

Expected:

```text
music unaffected
analysis marked unavailable
```

---

## OSC command is malformed

Expected:

```text
request rejected
runtime remains valid
```

---

## Future planning runs out

Expected:

```text
current safe deck continues indefinitely where possible
warning escalates
no silence
```

---

# 47. Master Safety

Always have:

```text
master limiter
```

Machine-check:

```text
peak <= configured ceiling
```

Default ceiling might initially be:

```text
-1 dBFS
```

Do not rely on the agent to manage clipping correctly.

---

# 48. Loudness

Measure:

```text
integrated LUFS
short-term LUFS
true/estimated peak
limiter reduction
```

Do not automatically normalize every section.

The purpose is preventing pathological output, not flattening musical dynamics.

---

# 49. Set-Level Automated Evaluation

After a rehearsal:

```bash
dj evaluate session/<id>
```

Produce:

```text
technical score
arc report
transition report
generation report
observation-response report
```

---

# 50. Technical Set Score

Objective components may include:

```text
audio continuity
clipping
runtime errors
generation misses
timeline underruns
failed transitions
buffer health
```

These can be binary or numerical.

---

# 51. Energy Arc Evaluation

Divide a set into windows.

For each:

```text
loudness
onset rate
spectral energy
bass energy
tempo
```

Derive a rough energy estimate.

Compare against intended arc.

For:

```text
warm → build → peak → release
```

the verifier can confirm that the measurable trajectory broadly follows the intended shape.

This does not prove the set is good.

It proves that the system is capable of producing intentional macrostructure.

---

# 52. Transition Evaluation

For each transition, calculate:

```text
loudness discontinuity
spectral discontinuity
tempo discontinuity
embedding discontinuity
unexpected silence
```

Large discontinuities generate warnings.

They are not always errors.

A deliberate hard cut should be allowed.

Therefore transitions should carry intent:

```json
{
  "style": "long_blend"
}
```

or:

```json
{
  "style": "hard_cut"
}
```

The verifier evaluates against the requested style.

---

# 53. Agent Behaviour Verification

Instrument CLI calls.

Then verify invariants such as:

```text
Did the agent maintain future coverage?

Did it schedule rather than sleep and issue commands at approximate times?

Did it inspect state before destructive actions?

Did it recover from generation failure?

Did it exceed BPM constraints?

Did it ignore set duration?

Did it make contradictory simultaneous transitions?
```

These are excellent agent-eval targets.

---

# 54. Scripted Agent

Do not require Codex itself for automated tests.

Implement:

```text
ScriptedDJ
```

A deterministic fake agent that uses the same public commands.

Example:

```text
start deck A
after 32 bars prepare B
after 64 bars transition A→B
change filter
finish
```

If ScriptedDJ works, the runtime/tool surface works.

If Codex fails afterward, the failure belongs to agent behaviour rather than audio infrastructure.

This separation is essential.

---

# 55. Coding-Agent Integration Test

Once the CLI is stable, provide an automated external-agent test task.

For example:

```text
Given this running test-mode DJ system:

1. inspect the current state;
2. start Deck A;
3. prepare Deck B;
4. transition at the next 16-bar boundary;
5. ensure future coverage remains > 30 seconds;
6. verify the resulting session.

Do not modify source code.
```

After Codex/Claude completes:

```bash
dj verify session latest
```

must determine pass/fail automatically.

The human should not need to judge whether the agent followed instructions.

---

# 56. Machine-Readable Everything

Every meaningful command needs:

```text
--json
```

Examples:

```bash
dj state --json
dj doctor --json
dj analyse A --json
dj verify --json
dj session report --json
```

Coding agents work better when they do not need to scrape decorative terminal output.

Human-readable output should remain available.

---

# 57. Session Storage

Structure:

```text
sessions/
  2026-08-31T2200/
    intent.yaml
    state.json
    events.jsonl
    decisions.jsonl

    renders/
      master.wav

    analysis/
      features.json
      verification.json
```

Generated temporary audio may live elsewhere if large.

---

# 58. Repository Structure

```text
agent-dj/
│
├── README.md
├── PROJECT_SPEC.md
├── AGENTS.md
├── SOUL.md
├── pyproject.toml
│
├── dj/
│   ├── cli.py
│   ├── config.py
│   ├── state.py
│   ├── events.py
│   ├── observations.py
│   ├── transport.py
│   │
│   ├── generator/
│   │   ├── base.py
│   │   ├── fake.py
│   │   ├── magenta_offline.py
│   │   ├── magenta_sc.py
│   │   └── magenta_core.py
│   │
│   ├── mixer/
│   │   ├── base.py
│   │   └── supercollider.py
│   │
│   ├── analysis/
│   │   ├── base.py
│   │   └── essentia.py
│   │
│   ├── verification/
│   │   ├── environment.py
│   │   ├── generator.py
│   │   ├── mixer.py
│   │   ├── timing.py
│   │   ├── continuity.py
│   │   ├── failure.py
│   │   └── session.py
│   │
│   ├── perception/
│   │   ├── base.py
│   │   ├── manual.py
│   │   ├── microphone.py
│   │   └── camera.py
│   │
│   └── tools/
│
├── supercollider/
│   ├── bootstrap.scd
│   ├── synthdefs/
│   │   ├── deck.scd
│   │   ├── mixer.scd
│   │   └── recorder.scd
│   └── tests/
│
├── native/
│   └── magenta_bridge/
│
├── fixtures/
│   ├── audio/
│   └── intents/
│
├── scripts/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── soak/
│
└── sessions/
```

---

# 59. Dependency Boundary

Every major external capability should implement an internal interface.

```text
Generator
Mixer
Analyzer
ObservationSource
Recorder
```

No business logic should import Magenta or Essentia directly outside their adapters.

This allows:

```text
Magenta → future model

SuperCollider → future DSP engine

Essentia → future analyser
```

without rewriting DJ policy.

---

# 60. Licensing Boundary

Do not vendor external model weights.

Do not silently redistribute third-party plugins.

Record dependency licenses.

Add:

```bash
dj licenses
```

which outputs:

```text
component
version
source
license
distribution mode
```

MRT2:

```text
code: Apache-2.0
model weights: CC-BY-4.0
```

Preserve required attribution.

Because the upstream SuperCollider plugin currently has unresolved licensing questions, treat it as:

```text
optional user-installed development dependency
```

until resolved.

Do not make project distribution depend on bundling it.

---

# 61. Generation Provenance

Store:

```text
generator
model
version
prompt
conditioning
seed where applicable
timestamp
```

for each generated segment.

Do not encourage prompts requesting imitation of identifiable artists.

The model provider explicitly places responsibility on users for generated-output rights.

The project's default prompt policies should prefer musical attributes:

```text
"hypnotic percussion-heavy techno"
```

rather than:

```text
"make exactly X artist"
```

---

# 62. Network Boundary

V0 should be local-first.

Performance should not require:

```text
cloud API
database
web service
account
login
```

Internet access may be required for:

```text
initial dependency installation
model download
```

but not for the live performance.

---

# 63. No Database Initially

Use:

```text
files + JSONL
```

until querying history becomes painful.

Do not introduce:

```text
Postgres
Redis
Kafka
Temporal
Kubernetes
```

to solve problems that do not yet exist.

---

# 64. Milestone 0 — Environment

Goal:

Codex can determine whether the computer is capable of running the stack.

Build:

```bash
dj doctor
```

Acceptance:

```bash
dj verify environment
```

returns success without human interaction.

The report must identify the usable Magenta backend.

---

# 65. Milestone 1 — Deterministic Audio Graph

No Magenta yet.

Implement:

```text
SuperCollider
Deck A
Deck B
master
crossfade
gain
filter
recording
test tones
```

Acceptance:

```bash
dj verify mixer
dj verify timing
dj verify continuity --minutes 2
```

all pass.

Human listening is optional.

Codex should not ask the user whether the crossfade worked.

It should record the audio and inspect it.

---

# 66. Milestone 2 — Offline Magenta

Implement:

```text
MagentaOfflineGenerator
```

Generate test material.

Acceptance:

```bash
dj verify generator --backend magenta-offline
```

automatically validates output.

Also record generation throughput.

---

# 67. Milestone 3 — Live Magenta

Implement a live adapter.

Preferred spike:

```text
upstream Magenta SuperCollider UGen
```

if available and functioning.

Otherwise:

```text
MagentaCoreGenerator
```

or a prebuffered chunk adapter.

The agent is allowed to inspect upstream examples and choose the shortest functioning implementation.

Acceptance:

```bash
dj verify generator --backend magenta-live
```

Must prove:

```text
continuous output
conditioning changes
runtime health
generation throughput
```

---

# 68. Milestone 4 — Two Generative Decks

Both decks produce independent Magenta material.

Acceptance:

```bash
dj verify dual-deck --minutes 5
```

Test:

```text
A playing
B preparing/generating
transition
B playing
A preparing
transition back
```

Requirements:

```text
no runtime crash
no audio starvation
no unplanned silence
```

---

# 69. Milestone 5 — Agent Tool Surface

Build CLI:

```text
state
generate
play
gain
filter
crossfade
analyse
schedule
```

Run deterministic ScriptedDJ.

Acceptance:

```bash
dj verify scripted-set
```

No LLM required yet.

---

# 70. Milestone 6 — Codex/Claude DJ

Provide `AGENTS.md`.

Ask external coding agent to perform:

```text
15-minute set
```

with defined constraints.

The session should be automatically evaluated.

Acceptance:

```bash
dj verify session latest
```

Technical pass must require no human judgment.

---

# 71. Milestone 7 — Manual Feedback

Implement:

```text
love
dislike
more-energy
less-energy
boring
weird
```

Run scripted feedback injection during a rehearsal.

The agent should alter future actions.

Acceptance:

The event log demonstrates:

```text
observation
→ agent decision
→ future scheduled change
```

without violating musical/runtime invariants.

---

# 72. Milestone 8 — Microphone

Add microphone observation adapter.

Begin only with low-level features.

Acceptance should use recorded crowd/noise fixtures before live microphone tests.

Example:

```bash
dj verify perception mic
```

feeds fixture audio and checks derived observations.

No human required.

---

# 73. Milestone 9 — Camera

Use recorded fixture videos before actual webcam operation.

Initial target:

```text
movement
movement_trend
people_visible
brightness
```

Acceptance:

```bash
dj verify perception camera
```

processes known fixture videos and validates approximate outputs.

---

# 74. Milestone 10 — Closed Feedback Loop

Run a synthetic room simulator.

This is important.

Create:

```text
FakeCrowd
```

FakeCrowd receives DJ actions and emits feedback.

Example policy:

```text
likes:
  124–130 BPM
  groove persistence
  percussion

dislikes:
  sudden energy drops
  excessive transitions
```

Then run:

```text
DJ → FakeCrowd → observations → DJ
```

for a simulated 60-minute session.

This makes the adaptive agent testable without assembling ten friends in a room.

---

# 75. Soak Testing

Provide:

```bash
dj verify soak --minutes 30
```

and later:

```bash
dj verify soak --hours 2
```

Collect:

```text
runtime crashes
audio underruns
memory growth
CPU
generation latency
late scheduler events
failed generations
master silence
```

Codex should inspect the report and fix failures autonomously.

---

# 76. Performance Report

After every set:

```bash
dj report latest
```

Example:

```text
SET: 2026-08-31T2200
DURATION: 01:02:14

TECHNICAL
✓ no runtime crashes
✓ no clipping
✓ no unexpected silence
✓ 14/14 generations completed
✓ 9/9 transitions executed

TIMING
average schedule error: 8.4 ms

GENERATION
average real-time factor: 0.63
worst: 0.91

ARC
warm    0.41
build   0.56
peak    0.81
release 0.48

FEEDBACK
12 observations
9 influenced subsequent decisions

WARNINGS
• Transition #7 produced unusually large spectral discontinuity
```

---

# 77. What Automated Verification Cannot Prove

Machine evaluation can establish:

```text
the music did not stop
the mixer works
the agent obeyed constraints
the transition occurred
the loudness is safe
the tempo is plausible
the set has measurable macrostructure
the output broadly aligns with conditioning
the system responded to feedback
```

It cannot establish:

```text
this is a fantastic DJ set
this groove is sexy
this transition feels perfect
the room genuinely loved it
```

Do not confuse those.

The project should minimize how often human verification is required, not pretend taste can be reduced entirely to unit tests.

---

# 78. Human Evaluation Boundary

Human evaluation should happen at:

```text
milestone-level
```

rather than:

```text
implementation-step-level
```

Good workflow:

```text
Codex implements feature
Codex runs verification
Codex fixes failures
Codex reruns verification
all technical tests pass
↓
human listens once
```

Not:

```text
Codex changes filter
"Can you listen and tell me if this worked?"
```

That interaction should be considered a test-design failure.

---

# 79. First Real Target

The first meaningful demo:

```text
30-minute autonomous generated set
```

Requirements:

```text
two Magenta streams/decks
continuous audio
agent-controlled transitions
agent-controlled prompt evolution
basic EQ/filter control
no human intervention
automated technical verification afterward
```

Input:

```text
Start with warm groovy house around 124 BPM.

Become progressively more hypnotic and darker.

Peak around 128–130.

Long blends.

Avoid cheesy drops and lots of vocals.

Do not stop the music.
```

---

# 80. First Delight Target

After the core works:

Place laptop in room.

Press:

```bash
dj start party.yaml
```

For the next hour:

```text
Codex/Claude
      ↓
Agent DJ
      ↓
Magenta
      ↓
SuperCollider
      ↓
speakers
```

Occasionally press:

```text
♥
↑
↓
W
```

and hear the future set adapt.

That is the first version worth showing people.

---

# 81. Later Delight Target

Add:

```text
microphone
webcam
```

Now:

```text
ROOM
 ↓
perception
 ↓
observations
 ↓
agent
 ↓
musical decisions
 ↓
ROOM
```

The system becomes a feedback loop rather than a generator.

---

# 82. Long-Term Possibility

The same architecture can eventually orchestrate:

```text
music
lighting
visuals
projection
smoke
venue effects
```

The DJ becomes:

```text
an agent controlling a room
```

rather than merely:

```text
an agent generating audio
```

Do not build that until the music system works.

---

# 83. Build Discipline

Codex/Claude must follow this order:

```text
deterministic audio
↓
verification
↓
Magenta
↓
two decks
↓
agent controls
↓
full set
↓
feedback
↓
mic
↓
camera
```

Do not jump to perception early.

---

# 84. Definition of Done for Any Feature

A feature is complete only if:

1. it has a stable agent-facing interface;
2. it has automated verification;
3. failure does not break unrelated live audio;
4. state is observable;
5. meaningful operations are logged;
6. no human listening is required to determine basic correctness.

---

# 85. Initial Codex / Claude Prompt

Use this after placing this specification into `PROJECT_SPEC.md`:

---

Read `PROJECT_SPEC.md` in full.

Your job is to build Agent DJ incrementally.

Do not attempt the entire project.

Begin with Milestone 0 and Milestone 1 only.

Before implementing:

1. inspect the local machine;
2. inspect current upstream Magenta RealTime 2 examples and APIs where relevant;
3. inspect the installed SuperCollider environment;
4. identify the shortest path to the deterministic two-deck test runtime.

Then implement:

- project skeleton;
- `dj doctor`;
- SuperCollider bootstrap;
- Deck A and Deck B buses;
- deterministic test-tone sources;
- master mixer;
- programmable crossfade;
- recording;
- `dj verify mixer`;
- `dj verify timing`;
- `dj verify continuity`.

Important constraints:

- do not add an LLM SDK;
- do not add Magenta yet unless needed only for environment detection;
- do not build a web UI;
- do not introduce a database;
- do not introduce containers or cloud infrastructure;
- Python must not participate in the real-time audio callback;
- use existing SuperCollider capabilities rather than writing DSP in Python.

Most importantly:

DO NOT ASK ME TO LISTEN TO AUDIO TO DETERMINE WHETHER THE IMPLEMENTATION WORKED.

Create deterministic audio fixtures, record the resulting master output and analyse the recording programmatically.

You should be able to determine yourself whether:

- both decks work;
- crossfading works;
- gain automation works;
- scheduling works;
- no unintended silence occurs.

Iterate autonomously until the milestone verification commands pass.

When finished, report:

1. architecture implemented;
2. exact commands used;
3. verification results;
4. failures encountered;
5. anything that genuinely cannot be verified automatically;
6. the smallest recommended next milestone.

Do not start Milestone 2 until Milestone 1 passes.

---

# 86. Guiding Sentence

When in doubt:

> The agent chooses what the music should do; existing tools make the audio do it; automated verification proves the machinery actually worked.
