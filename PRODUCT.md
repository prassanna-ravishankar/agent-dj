<!-- impeccable:product-schema 1 -->

# Agent DJ — Product Definition

Durable product truth for Agent DJ, derived from the working system rather than from intent.
Every claim below is traceable to a file in this repository. Where something is unproven or
unbuilt, it says so.

Sources: `README.md`, `PROJECT_SPEC.md`, `SOUL.md`, `AGENTS.md`, `dj/` (CLI, models, policy,
runtime, mixer, observations, events, scheduler), `supercollider/`, `sessions/` artifacts.

**Document contract.** Sections 1–13 are product truth: claims about what the system is and
does, each traceable to a file. They constrain any surface built on this product and should
outlive any particular design. Appendix A is visual prescription: one committed design language
among several that could satisfy the truth above. Truth does not change when the design changes.
If the two ever conflict, the truth sections win and the appendix is wrong.

---

## Platform (web)

The delivered surface is a **local web application**, served from and reachable only on the
performer's own machine. It is a control and observation surface, never the system of record.

- **Local-only.** No hosting, no external network at performance time. The page is served by a
  local process alongside the runtime it observes (`PROJECT_SPEC.md` §62; `doctor.py` reports
  `local_only: True`).
- **Non-authoritative.** State lives in `sessions/<id>/state.json` and the JSONL logs. The browser
  renders that state and issues commands the CLI already exposes. It computes nothing the system
  depends on.
- **Disposable.** Closing the tab, reloading, or losing the browser entirely does not affect
  audio. This is the same guarantee already extended to the control plane and the agent
  (`PROJECT_SPEC.md` §46).
- **Not on the audio path.** No decoding, no playback, no scheduling that audio correctness
  depends on. The browser cannot break the music, and should visibly read that way.
- **Two real form factors.** A desktop performance console and a genuinely useful mobile remote
  on the same local network. Neither is a degraded version of the other; see §9.

### Standing constraint, recorded honestly

`PROJECT_SPEC.md` line 3059 lists "do not build a web UI" among the constraints of the
**Milestone 0/1 bootstrap prompt** (§85), alongside "do not add an LLM SDK" and "do not add
Magenta yet" — both since intentionally superseded as milestones advanced. That constraint is
scoped to the initial bootstrap, not a permanent product prohibition. It is recorded here so the
decision is explicit rather than accidental: a web surface is built *after* the CLI and
verification layers are real, and it never becomes the system of record.

---

## Stack

Chosen by the frontend lead; the choice was explicitly delegated.

| Layer | Choice |
|---|---|
| Build | Vite |
| UI | React 18 |
| Language | TypeScript (strict) |
| Styling | Plain CSS — custom-property tokens plus CSS Modules |
| State | One reducer over a typed adapter; no state library |
| Routing | Two routes, hand-rolled; no router library |
| Test | Vitest + Testing Library |
| Local server | Small Starlette/FastAPI process: shells `dj <cmd> --json`, tails session JSONL, serves the static build |

**No UI kit and no CSS framework.** The committed visual language (Appendix A) is
material-and-grid specific in ways a component library actively resists; adopting one would mean
overriding its defaults everywhere, and those defaults are precisely the generic dashboard
idiom this product must not look like.

**TypeScript is load-bearing, not preference.** The adapter is a typed mirror of the Pydantic
models in `dj/models.py`. Nullable fields must stay nullable all the way to the component, or the
surface will silently render absent measurements as zeros — see §4 and §13.

**React earns its place** on one screen: the observation → decision → schedule → event chain is
an append-only, grouped, keyboard-navigable list. The rest of the app would be content with far
less.

Constraints inherited from the product: no database (`PROJECT_SPEC.md` §63), no containers, no
cloud, no network at performance time, and no capability in the UI that the CLI does not already
expose.

---

## 1. What the product is

Agent DJ is a local-first autonomous generative music performer. It runs an entire live
electronic set on one machine: generating musical material, holding it on two decks, mixing and
transitioning between them, and adapting the trajectory of the set from observations.

It is not a playlist generator, not a song generator, and not a DAW (`PROJECT_SPEC.md` §1). Its
own contribution is orchestration: state, tool interfaces, musical scheduling, observations,
agent-readable context, verification, failure isolation, and set history (§2). Anything a mature
tool already does well is wrapped, not reimplemented.

### The unique mechanism

**A generative music system whose creative loop is deliberately severed from its audio loop:
SuperCollider holds an unbreakable safe playback floor while a slower, fallible reasoning layer
races to keep a measurable "future coverage" horizon populated — so the set can be surprised,
degraded, or abandoned by its own intelligence without the music ever stopping.**

This is the thing worth designing around. It is not "an AI DJ." It is a system with an explicit,
instrumented safety margin between what is currently guaranteed to play and what has merely been
decided.

---

## 2. Fixed product truths

These are non-negotiable and hold across every surface.

| Truth | Evidence |
|---|---|
| Everything runs locally. | `README.md`; `doctor.py` reports `local_only: True`; network needed only for initial dependency/model install (`PROJECT_SPEC.md` §62). |
| Magenta RealTime 2 generates material. | `dj/generator/magenta_live.py`, `models/models/mrt2_small/`, `dj generate`. |
| SuperCollider owns playback, decks, DSP, crossfade, limiter, recording, continuity. | `supercollider/bootstrap.scd`, `dj/mixer/supercollider.py`, `README.md` architecture note. |
| Music must not stop. | `AGENTS.md` (highest-priority runtime invariant); `PROJECT_SPEC.md` §46. |
| Python never enters the real-time audio callback. | `AGENTS.md`; `PROJECT_SPEC.md` §5. |
| A safe deck loops if the control process or agent disappears. | `README.md`; `verify continuity`; `PROJECT_SPEC.md` §46 "Agent disappears → audio continues". |
| Every meaningful command emits machine-readable output and appends an operational event. | `AGENTS.md`; every CLI command carries `--json`; `dj/events.py`. |
| Decisions are recorded concisely; private reasoning traces are not. | `AGENTS.md`; `decisions.jsonl` records goal/evidence/actions only. |

The browser's role and the standing web-UI constraint are stated under **Platform (web)** above.

---

## 3. Architecture as the user must understand it

```text
human feedback ─┐
future mic ──────┼─> Observation JSONL ─> local policy ─> generate + schedule
future camera ───┘                                  │
                                                   OSC
Magenta RT 2 ─> prepared stereo buffers ─> SuperCollider decks/mixer ─> audio
```

Three processes, independently killable:

1. **Audio runtime** — `sclang` running `bootstrap.scd`, started by `dj start`. Liveness is a
   `.runtime-ready` file plus a live PID (`dj/runtime.py`). This is the only thing that must not
   die.
2. **Local agent worker** — `python -m dj.agent_worker`, started by `dj agent start`. Polls
   observations every 200ms, decides, generates, schedules. Liveness is `.agent-ready` + PID
   (`dj/agent.py`). Its absence is survivable and must be shown, not hidden.
3. **Control plane** — the `dj` CLI itself, and any future web surface. Stateless per
   invocation; reads and writes session files.

Two clocks (`PROJECT_SPEC.md` §6): the **audio clock** (sample-accurate, SuperCollider's) and the
**musical/agent clock** (bars and phrases, derived). Scheduling is expressed in bars, executed
against wall time via `current_bar()` (`dj/scheduler.py`). Any surface that shows time must
respect that these are different, and that bars are the language of musical intent.

---

## 4. Canonical state

From `dj/models.py`. This is the complete shape a surface can render — inventing fields beyond it
would be inventing capability.

```
DJState
  session_id            str
  status                str            "development" | "live" | "stopped"
  transport             playing, bpm (default 124), bar, beat, started_at, sample_position
  decks                 { A: DeckState, B: DeckState }
  master                peak_dbfs, lufs_short, limiter_reduction_db   (all nullable / 0)
  future                covered_until_bar, estimated_seconds
  observations          last 100 observation dicts
  updated_at            datetime

DeckState
  name, status, source ("fake" | "magenta"), prompt, gain_db (default -60),
  energy (0..1, nullable), audio_path, duration_seconds

DeckStatus  stopped | preparing | prepared | playing | failed
```

Notable and design-relevant:

- `energy` is `None` until the agent has moved it. It is agent-maintained, clamped 0..1, adjusted
  by `energy_delta` per feedback kind. It is **not** measured from audio. A surface must not
  present it as an analysis result.
- `master.peak_dbfs` and `lufs_short` are `null` in every recorded session artifact. Loudness
  metering is specified (§48) but not yet wired into state. **A surface must render these as
  genuinely unavailable, not as zero.**
- `gain_db` default is `-60`, i.e. silent-but-loaded, not 0. Off-air decks sit at -60.
- `future.estimated_seconds` is set to `86_400` (one day) once any safe looping buffer exists —
  a sentinel meaning "indefinite", because JSON cannot represent infinity (comment in
  `dj/runtime.py`). **A surface must never render "24 hours of coverage".** It means *safe*.

### Future coverage thresholds

From `dj/config.py` `CoverageConfig`, and `PROJECT_SPEC.md` §17:

```
normal    >= 90 seconds
warning   <  60 seconds
critical  <  30 seconds
```

Configurable. The agent refuses a creative change below critical when no safe buffer exists
(`agent_worker.py` raises "cannot make creative change without a safe playing buffer"). "Continue
the current deck" is always a valid outcome; running out of plan is never a reason to stop.

---

## 5. Clock integrity

The musical clock is **derived, not stored**. `current_bar()` (`dj/scheduler.py`) computes the
current bar from wall-clock elapsed time since `transport.started_at`, divided by
`seconds_per_bar`. Nothing writes `transport.bar` during a live set — `grep` finds only reads.
There is no heartbeat and no drift correction against the audio clock.

Every bar number a surface displays is therefore an inference from two stored fields
(`started_at`, `bpm`) and the local time of the machine reading them. It can be wrong. Since the
committed design makes bars the primary spatial unit, a wrong clock is not a cosmetic defect —
it corrupts the central metaphor. The surface must be able to say so.

### Confirmed defects in recorded data

Measured across all 14 sessions under `sessions/`, not hypothesised:

| # | Defect | Extent |
|---|---|---|
| 1 | `started_at` is **later than** `updated_at` — the state file is written before the transport start timestamp is persisted | 11 of 14 sessions; skew from 2.8s to 135.9s |
| 2 | `status: "stopped"` while `transport.started_at` remains populated — `runtime.stop()` clears `playing` and `status` but never nulls `started_at` (`dj/runtime.py`) | 13 of 14 sessions |
| 3 | `transport.bar` is `0` in every recorded session and is never written during a set | 14 of 14 sessions |

Defect 2 is the dangerous one: a stopped session still carries a start timestamp, so a naive
reader computing elapsed time gets a bar number that grows forever on a system producing no
audio. The guard is `transport.playing`, which `current_bar()` checks first — any surface must
check it too, and must not treat a non-null `started_at` as evidence of playback.

### The `clock_uncertain` state

A derived state the surface computes; it is not a field in `DJState`. It is **not an error** —
the music is unaffected, and audio correctness never depended on this clock. It means only:
*this display cannot honestly claim a bar position right now.*

Raised when any of:

| Trigger | Test |
|---|---|
| Future start | `started_at > updated_at`, beyond a small tolerance |
| Contradiction | `status == "live"` but `playing == false`, or `playing == true` with `started_at == null` |
| Stale state | `updated_at` older than a staleness window while `status == "live"` |
| Stopped-but-timestamped | `playing == false` with `started_at` populated, and elapsed time is being derived |
| Implausible tempo | `bpm` outside the CLI's own accepted 40–240 range (`dj generate --bpm`) |
| Reader clock skew | local time earlier than `updated_at` |

**Required behaviour.** Every derived value — the bar counter, the horizon's scroll position,
scheduled-item placement, and all "lands in N bars" countdowns — becomes explicitly
indeterminate rather than showing a plausible wrong number. Values known to be stored rather
than derived (deck status, prompts, gain, coverage seconds, the chain) continue to display
normally, because they remain true. The state names its trigger in plain language, and offers
re-reading state as the resolving action. It is announced politely to assistive technology, not
assertively: nothing is on fire.

**What it must never do:** substitute a fallback bar number, freeze at the last good value while
appearing live, or degrade into a generic error screen that hides the deck and coverage
information that is still perfectly valid.

---

## 6. The observation → decision → schedule chain

This chain is the product's legible core and the thing a performer most needs to read. It is
fully materialized on disk, per session.

```
observations.jsonl   Observation  { id, source, kind, value, confidence, timestamp, metadata }
        ↓ LocalDJPolicy.decide()  — deterministic, no LLM, no network
decisions.jsonl      { goal, evidence[], actions[], observation_id, decision{...} }
        ↓
schedules.jsonl      { id, created_at, status, action, target, at_bar, parameters }
        ↓
events.jsonl         append-only operational log
```

The observation boundary is **source-neutral** by design: a human tapping "more energy", a future
microphone, and a future camera all produce the same `Observation` shape. `manual_feedback()`
stamps `source="human"`, `confidence=1.0`. Microphone (§31) and camera (§30) are later milestones
and are **not built** — a surface may reserve room for them but must not imply they exist.

### Feedback vocabulary and what each actually does

From `dj/policy.py` — deterministic, fully enumerable. This is real product behaviour, not
suggestion:

| Feedback | Goal | Transition | Energy Δ |
|---|---|---|---|
| `love` | reinforce what is working without a sharp change | 8 bars | +0.05 |
| `dislike` | move to a coherent alternative direction | 4 bars | −0.05 |
| `more-energy` | increase energy through density and drive | 4 bars | +0.20 |
| `less-energy` | release energy while preserving continuity | 8 bars | −0.20 |
| `boring` | introduce novelty without abandoning the set | 4 bars | +0.10 |
| `weird` | take a controlled unexpected detour | 4 bars | +0.05 |

Two structural facts worth surfacing to the performer:

- **Feedback always targets the off-air deck.** The policy picks the deck that is *not* playing
  and prepares the response there. Feedback is never an edit to what you are currently hearing.
- **Approval is the slowest gesture.** `love` and `less-energy` take 8 bars; everything
  disruptive takes 4. The system is more patient when asked to keep going than when asked to
  change — consistent with `SOUL.md`: "If something works, allow it to work."

Live transitions are phrase-aligned: `next_phrase_bar(now, 4)` in production
(`agent_worker.py`). A commanded change waits for the phrase. That latency is musical
correctness, not lag, and any surface must present it as such.

---

## 7. Event vocabulary

Observed across all recorded sessions in `sessions/*/events.jsonl` (counts from real artifacts):

```
transition_started      transition_scheduled     schedule_executed
runtime_started         runtime_stopped          session_created
generation_requested    generation_started       generation_ready      generation_failed
parameter_changed       state_inspected          set_intent
recording_started       recording_stopped        analysis_completed
observation_received    observation_processed    agent_decision
scripted_set_started    scripted_set_completed   deck_started
warning                 error
```

`warning` carries `kind` (e.g. `future_coverage_critical`); `error` carries `subsystem` and
`error`. Events are append-only, one JSON object per line, `ts` + `type` + payload
(`dj/events.py`).

---

## 8. Core user actions

Everything a performance surface must support, each backed by an existing CLI command:

| Action | Command | Notes |
|---|---|---|
| See runtime health | `dj status --json` | `{ok, running, pid, local_only}` |
| See agent health | `dj agent status --json` | same shape; absence is survivable |
| Inspect environment | `dj doctor --json` | platform, SC, Magenta, storage, models |
| Read full state | `dj state --json` | canonical `DJState` |
| Inspect future coverage | from `state.future` | against normal/warning/critical |
| Generate material | `dj generate A --prompt "..." --bpm --duration` | slow, fallible, off the audio path |
| Bring a deck on air | `dj play A` | requires prepared audio; 0.25s safe fade |
| Transition | `dj crossfade B --bars 16` | bars, not seconds |
| Gain | `dj gain A -4` | dB |
| Filter | `dj filter A lowpass 2200` | lowpass \| highpass only, as implemented |
| Record | `dj record start` / `stop` | master bus → `sessions/<id>/renders/master.wav` |
| Feedback | `dj feedback <kind>` | the six kinds above |
| Read the chain | `events.jsonl`, `decisions.jsonl`, `observations.jsonl` | append-only |
| Start/stop runtime | `dj start`, `dj stop` | refuses live start with no prepared deck |
| New session | `dj session-new --id X` | refuses while runtime or agent is running |

Implemented effect vocabulary is **lowpass and highpass only** (`mixer/supercollider.py` raises
on anything else). Delay, reverb, and EQ appear in the spec (§22–23) but are not built. A surface
must not offer them.

---

## 9. Critical states

These must be unmistakable at a glance, in any lighting, at any distance a performer actually
stands from the screen.

| State | Source of truth | Why it matters |
|---|---|---|
| **Offline** | runtime `running: false` | no audio is being produced by this system |
| **Agent absent** | agent `running: false` | survivable; music continues; no new decisions |
| **Preparing** | `DeckStatus.PREPARING` | generation in flight; not yet safe to transition to |
| **Safe** | coverage ≥ normal, or looping buffer sentinel | the invariant is currently held |
| **Coverage warning** | `< 60s` | act soon |
| **Coverage critical** | `< 30s` | act now; agent will refuse creative change without a safe buffer |
| **Generation failure** | `generation_failed` / `DeckStatus.FAILED` | deck unusable; other deck continues |
| **Command pending** | issued, no confirming event yet | phrase-aligned waits are normal, not hangs |
| **Recording** | `recording_started` without `recording_stopped` | destructive to forget |
| **On-air deck** | the deck with `DeckStatus.PLAYING` | the single most important fact on screen |
| **Clock uncertain** | derived; see §5 | bar position cannot be honestly claimed; music unaffected |

The failure contract (`PROJECT_SPEC.md` §46) that a surface must visibly honour: agent dies →
audio continues; deck B generation fails → deck A continues, transition cancelled, warning
emitted; analysis dies → music unaffected, analysis marked unavailable; malformed command →
rejected, runtime remains valid; planning runs out → safe deck continues, warning escalates, no
silence.

---

## 10. Who uses it and when

**The performer, mid-set, standing up, hands occasionally busy, in a dark room.** They are not
reading. They are glancing. The questions they ask, in frequency order:

1. Is it still playing, and which deck?
2. Am I safe — how far ahead is the music covered?
3. Did the thing I just asked for land, and when will I hear it?
4. What is coming next, and why did it decide that?

**The same person before the set,** at a desk, checking `doctor`, generating starting material,
verifying both decks are loaded.

**A coding agent,** operating the same CLI surface — the external agent boundary (§14) is the CLI,
and any web surface must not become a privileged second path that agents cannot use.

### Two sizes, both real

- **Desktop performance console.** Primary. Glanceable at arm's length or further. Keyboard
  operable throughout — a performer with one hand on a controller should not need a pointer.
- **Mobile remote.** Genuinely useful, not a shrunken console. The performer is away from the
  laptop: they need on-air deck, coverage, transport, the six feedback gestures, and a way to see
  that a command landed. Generation prompting and fine mixer work can degrade gracefully.

### Non-negotiable qualities

Accessibility, full keyboard operation, `prefers-reduced-motion` respected, and honest
loading / error / empty states are requirements, not polish. A surface that animates a
coverage meter into a performer's peripheral vision during a set has actively made the product
worse.

---

## 11. Aesthetic policy

`SOUL.md` is the long-term aesthetic identity, stored separately from any single set's intent
(§19):

> Groove over novelty. Patient. Likes percussion, hypnotic repetition, long blends, bass
> movement, slow transformations, subtle tension, occasional unexpected euphoria. Dislikes cheesy
> drops, unnecessary vocals, restless direction changes, obvious clichés. Higher BPM does not mean
> higher energy. If something works, allow it to work.

Set intent (§18) is per-session and structured: duration, BPM range, styles per phase, arc,
preferences, special instruction. **Only `planned_duration_minutes` is currently implemented**
(`dj session-new --duration-minutes` → `set_intent` event). The richer intent schema is specified
and unbuilt.

A surface should feel like this personality. Patience, restraint, and long gestures are product
truth, not decoration.

---

## 12. What is real, and what is not

Stated plainly so no surface invents capability.

**Built and verified.** Two decks with independent gain and lowpass/highpass filtering;
programmable crossfade; master limiter; recording; deterministic test-tone mode; local MRT2
generation via MLX (prebuffered, faster than realtime); the source-neutral observation boundary;
deterministic local policy; bar-aligned scheduling; the append-only event/decision/observation
chain; session persistence; the full `dj verify` suite; a scripted DJ driving the same public CLI
an external agent uses.

**Specified, not built.** Microphone and camera observation; delay/reverb/EQ; `--over-bars`
parameter ramps; the full set-intent schema; loudness metering into state; set-level scoring and
performance reports; the native MRT2 `RealtimeRunner` bridge (the adapter boundary is ready, the
current live adapter is prebuffered).

**Deliberately absent.** No database (§63). No containers or cloud infrastructure. No LLM SDK in
the runtime path — the live policy is deterministic Python. No network at performance time.

**Not claimed.** No commercial claims, no comparative claims, no claims about musical quality.
The project's own verification principle (§34) is that machines check machine-checkable things
and that automated verification cannot prove a set was good (§77) — human musical judgment
remains outside the system's ability to assert. A surface must not imply otherwise.

---

## 13. Binding design constraints

What the truth above forces on **any** surface, before and independent of any visual decision.
These outlive Appendix A. A different design language must still satisfy every one of them.

1. **Safety margin is the primary subject.** Not levels, not waveforms. The one quantity that
   governs whether the invariant holds is how far ahead the music is covered.
2. **Two decks, asymmetric.** Exactly two, and never equal — one is on air. Composition must
   express that asymmetry rather than presenting a symmetric pair.
3. **Latency is musical, not technical.** Commands land on phrase boundaries. Pending must read
   as "waiting for the bar", with the bar visible, never as an unexplained spinner.
4. **Null is not zero.** Loudness fields are genuinely unavailable today. Absent, empty, and zero
   are three distinct states and must be distinguishable.
5. **`86_400` means "safe", not "a day".** Render the sentinel as a state, never as a duration.
6. **Every bar number is an inference.** The musical clock is derived and uncorrected. A surface
   that displays bars must be able to withdraw that claim (§5) rather than show a confident wrong
   number.
7. **The chain is a first-class reading surface.** Observation → decision → schedule → event is
   how a performer understands the system's mind. It is content, not a debug log; `goal` and
   `evidence` are already written in human language.
8. **Degradation is a designed state.** Agent absent is a normal, survivable mode the product is
   proud of. It must look deliberate and calm, never like an error.
9. **The browser must look like it cannot break the music.** The surface should read as an
   observation deck attached to a running machine, not as the machine itself.
10. **No capability beyond the CLI.** If `dj` does not expose it, the surface does not offer it.
    Lowpass and highpass exist; delay, reverb, and EQ do not.

---

# Appendix A — Committed visual language

**This appendix is prescription, not truth.** It is one design language chosen to satisfy §13.
It may be replaced without any section above changing. Where it appears to contradict the truth
sections, the truth sections are correct.

## A.1 Direction: The Horizon

Composition is organised around the coverage margin as literal space. The left edge is **now** —
on-air, guaranteed. Rightward is **the future you have bought yourself**. Bars are the horizontal
unit, so phrase-aligned latency reads as *distance* rather than delay. Two deliberately
asymmetric deck bodies sit beneath it, one lit. Everything else docks to that band.

It is derived from the safety mechanism (§5, §13.1) rather than from a dashboard category, and it
degrades correctly: agent absent means the horizon stops being *extended* while the guaranteed
floor stays lit — which is exactly the truth of the system.

### Directions considered and rejected

| Direction | Why rejected |
|---|---|
| Mixing-desk skeuomorph | Lies about scale. Two decks, gain + lowpass/highpass only, master metering `null`. A desk implies channel count and metering fidelity that do not exist, and frames the human as the mixer when SuperCollider is. |
| DAW / timeline arrangement | Past-oriented, and `PROJECT_SPEC.md` §1 explicitly says not a DAW. The live questions are all *now* and *next*; a timeline optimises for scrubbing, the one thing you cannot do to a live set. |
| Terminal / ASCII console | Honest to the CLI-first product but fails the mobile remote badly, and fails glanceability — a monospace wall is unreadable at 2m in a dark room. Its honesty survives as texture in the chain view. |

## A.2 Challenger evaluation

Three external concept seeds were tested against The Horizon on **audience identification** and
**product clarity**. Two contributed grammar; one was rejected outright.

### Cassette-futurist fascia — *grammar borrowed, whole rejected*

Brushed panel, explicit labelled switches, amber active channel. Its valuable grammar is
**permanent explicit labelling**: a control that states its own consequence in print, always,
rather than on hover.

This fits unusually well because the feedback consequences are *fixed and enumerable* — `love` is
always 8 bars and +0.05 (§6). Those constants can be printed on the control itself, permanently.

Rejected as a whole language on **audience identification**: a fascia asserts "this panel *is*
the machine." The browser explicitly is not (Platform §, §13.9). Adopting the full idiom would
misrepresent the product's defining severance, and would import a nostalgia the product has not
earned — SOUL.md values patience and restraint, not retro affect.

**Fused:** every feedback control permanently prints its own consequence — `MORE ENERGY · 4 bars
· +0.20`. The performer never has to learn or recall the policy table; it is on the surface.

### Miura deployable sheet — *rejected outright*

Linked crease geometry where one action propagates across the future field. The most seductive
and the most dangerous of the three.

Rejected on **product clarity**, decisively: it implies coupling that does not exist. Decks are
independent. A feedback gesture prepares the *off-air* deck and schedules exactly one crossfade
(§6). Nothing propagates, nothing cascades, no single action reshapes a field. A crease metaphor
would be beautiful and would be a lie about the mechanism — spectacle over truth, and the product
record is explicit that truth wins.

It also fails audience identification: a performer needs to know precisely *what* changes and
*when*. Propagating geometry communicates diffuse influence, which is the opposite of a
bar-accurate scheduled commitment.

**Fused: nothing.** Recorded here so the rejection is deliberate rather than an oversight.

### Seven-segment instrument family — *strongest contribution*

Designed unlit ghost segments, fixed cells, instant state swaps. This carries the single best
idea in the challenger hand, and it solves a problem the design already had.

The **unlit ghost segment** is the canonical solution to §13.4. Loudness is genuinely unavailable
(`peak_dbfs` and `lufs_short` are `null` in every recorded session). A ghost segment shows *this
cell exists and its value is absent* without inventing a zero — structurally distinguishing
absent from empty from zero, which no amount of colour choice achieves as cleanly.

**Fixed cells** serve glanceability directly: digits occupy reserved space and never reflow, so a
performer's eye returns to the same physical position. This subsumes the earlier tabular-numerals
requirement and strengthens it. **Instant state swaps** suit a product whose real state changes
are discrete and bar-quantised — a crossfade completes on a bar, it does not ease.

**Fused, three ways:**
1. Ghost segments are the standard rendering for every unavailable measurement — loudness above
   all, and any deck field that is `null`.
2. All numeric readouts occupy fixed cells: bar, BPM, gain, coverage seconds, energy.
3. Ghost segments become the display for `clock_uncertain` (§5). When the bar position cannot be
   honestly claimed, the bar counter shows its unlit cells. The instrument is visibly present and
   visibly not asserting a value — precisely the required behaviour, and far better than the
   indeterminate treatment originally sketched.

### Verdict

**The Horizon remains the committed direction**, strengthened by fused grammar from two
challengers. The spatial argument is unchanged; what improves is how honestly individual values
report themselves. The Miura seed is rejected on record.

## A.3 Design language

**Palette — "one light source".** Not neon-on-dark. Warm near-black ground (`#0E0D0C`, slightly
brown, not blue) with a single amber-white emissive that only ever means *on-air / guaranteed*.
Colour is spent, not decorated: amber = live and safe; cold slate = prepared but silent (the
−60 dB truth); ember-orange = coverage warning; one high-chroma red reserved exclusively for
critical coverage and recording. Off-air is genuinely darker, not merely a different hue. One
gradient exists in the entire design — on the horizon band, encoding coverage falloff.

**Type — two families.** A tight grotesque (Inter Tight, `system-ui` fallback) for labels and
prose. A tabular monospace (JetBrains Mono, `ui-monospace` fallback) for every number a performer
compares over time. Fixed cells and tabular numerals are mandatory: digits must not reflow.
Numbers large and few; labels small, uppercase, wide-tracked, low-contrast so they recede at a
glance and remain available on inspection.

**Material — "lit panel, not floating card".** No drop shadows, no rounded rectangles floating on
a dark field. Surfaces are flush, separated by 1px hairlines and small luminance steps, like an
instrument fascia. Depth comes from light falloff, not elevation. The on-air deck is the only
surface that emits. One texture: very low-opacity fine grain (SVG fractal noise) so large dark
areas do not band on booth projectors.

**Controls — "gesture over widget".** The six feedback kinds are primary: large flat
keyboard-numbered targets (1–6), each permanently printing its own consequence. Transport and
mixer controls are secondary and physically smaller. Crossfade is a bar-denominated commitment
(4/8/16/32), not a draggable slider, because bars are the actual vocabulary. Gain and filter are
steppers with typed entry — a slider implies precision and real-time responsiveness the OSC
boundary does not promise.

**States — shape or position, never colour alone.** On-air: lit body plus persistent left-edge
marker. Preparing: horizontal indeterminate fill, no spinner. Pending: the command echoes onto
the horizon at its target bar, counting down *in bars*. Recording: persistent red hairline along
the full top edge of the viewport. Offline: the ground loses amber entirely; a plain statement
replaces the horizon. Agent absent: horizon dims past *now*, stating "no new decisions — deck A
continues"; calm, not an error colour. Clock uncertain: ghost segments in every derived cell,
trigger named in plain language. Coverage sentinel `86_400` renders as the word **SAFE**. Null
loudness renders as ghost segments plus "unavailable", never `0`.

**Motion — reserved for what is actually moving in the music.** The bar counter advances; the
horizon scrolls at transport rate. Nothing else animates: no entrance animations, no hover lifts,
no pulsing. State changes are 120 ms luminance cross-fades; discrete swaps are instant. Under
`prefers-reduced-motion` the horizon stops scrolling and steps once per bar, and the transport
becomes a static readout — a real alternate mode, not durations set to zero.

**Terminology — the product's own words.** "On air" not "active". "Covered until" not "buffer".
"Lands in N bars" not "pending". "Prepared" not "loaded". "Decision" and "evidence" verbatim from
`decisions.jsonl`. "Safe" has a specific meaning and is never used loosely.

## A.4 First viewport and signature interaction

- **Top hairline** — recording indicator (only while recording); runtime and agent health as two
  small hard-edged status blocks, left.
- **Upper third — the horizon.** Full-bleed band. Left edge is now, marked with the current bar
  in large fixed-cell mono. Coverage extends rightward as a lit region falling off into the
  ground; the falloff point is labelled in both seconds and bars. Scheduled changes appear as
  vertical ticks at their target bar, each labelled with the `goal` text from the decision.
  Warning and critical redraw the falloff in ember/red and pull it visibly close to now.
- **Middle — two deck bodies, asymmetric.** The on-air deck is roughly 1.6× the width of the
  off-air one, lit, showing prompt, source, energy, gain, elapsed. The off-air deck is dark,
  showing its prepared prompt and readiness. They swap size and light during a crossfade, over
  the actual crossfade duration.
- **Lower third** — the six feedback gestures in one row, each printing its consequence.
- **Right rail (desktop) — the chain.** Reverse-chronological, grouped by `observation_id`, so
  one tap of "more energy" reads as a single entity that grew a decision, a generation, and a
  scheduled transition.

**Signature interaction — "commit to the bar".** Press a feedback key or tap a gesture. Instead
of a toast, the consequence is drawn onto the horizon as a ghost tick at the phrase-aligned bar
where it will land, its width the policy's transition length, with a faint preview of the deck
swap. It is visibly *a thing placed in the future*, not a button that fired. As bars advance the
tick travels left toward now; on execution it solidifies and the decks actually swap. The
performer learns the system's patience by watching their own intent travel. This is the product
in one gesture: you influence the future, the present stays guaranteed.

## A.5 Information architecture

**Desktop console (≥1280px).** Single non-scrolling viewport, four horizontal registers plus the
persistent chain rail. Nothing important below the fold. Secondary surfaces (doctor/environment,
session picker, generation prompting) live on a second route framed as *pre-set* — calmer,
denser, the desk-at-rest mode.

**Mobile remote (≤640px).** Not a shrunken console. Vertical priority stack: (1) on-air deck plus
current bar, (2) coverage as a single word plus number, (3) the six gestures as a 2×3 thumb-sized
grid, (4) collapsed chain, expandable. Prompting, filter, and gain are demoted to a sheet.
Recording indicator stays pinned. Target: answer *is it playing, am I safe, did my gesture land*
with zero scrolling.

**Between (tablet / booth screen).** Horizon, decks, gestures; the chain collapses to a single
most-recent-decision line.

**Keyboard.** `1`–`6` feedback; `A`/`B` deck focus; `space` plays the focused deck; `C` crossfade
then a bar-count digit; `R` record toggle with confirm; `/` jumps to the chain; `?` shortcut
overlay. Visible focus rings throughout, logical tab order, and an ARIA live region announcing
on-air deck changes, coverage threshold crossings, command landings, and `clock_uncertain` at
**polite** — **assertive** reserved for critical coverage and generation failure.

## A.6 Known risks

- The horizon depends on `at_bar` being meaningful and `current_bar()` being accurate. §5
  documents three confirmed defects in recorded data; `clock_uncertain` is the designed answer,
  but the metaphor is only as good as that state's honesty.
- `future.estimated_seconds` is `86_400` in almost all recorded artifacts and `covered_until_bar`
  is `0` in most. The horizon's most interesting range (30–90 s) may be rare in practice — it
  risks being a beautiful visualisation of a constant. Wants validation against a real
  Magenta-backed session.
- Two decks and null metering mean the middle of the screen genuinely holds less data than
  dashboard instinct wants. Risk of styling emptiness as elegance when it is missing information.
- Polling versus SSE against JSONL tails needs measurement across a long set, not assumption.
- No audio in the browser means no waveform, no spectrum, no meters. Some instrument feel people
  expect from a "DJ UI" is structurally unavailable by design; the language must earn it from
  typography, light, and timing instead. That is a real bet.
- Grain over large dark fields can band on some projectors and OLED panels; needs booth hardware
  testing not available here.

## A.7 Assets

No bitmap assets required. The single texture needed is fine grain, better implemented as an SVG
fractal-noise filter than a bitmap: crisp at any DPI, themeable, near-zero bytes. No deck art, no
mark, no photography.

---

# Appendix B — Phase-2 implementation boundary

Scope for the implementation phase. Also prescription, not truth.

## B.1 File boundary

All new code confined to a new top-level `web/`. **Zero changes to `dj/`, `supercollider/`,
`tests/`, `pyproject.toml`, or any existing file.** No commits.

```
web/
  src/adapter/types.ts      hand-written mirror of dj/models.py
  src/adapter/client.ts     the ONLY module that talks to the backend; Result<T, AdapterError>
  src/adapter/coverage.ts   pure: seconds -> 'safe'|'normal'|'warning'|'critical', incl. 86_400
  src/adapter/clock.ts      pure: derives bar position and the clock_uncertain state (§5)
  src/adapter/policy.ts     pure: feedback consequence table, mirrored for preview only
  src/adapter/chain.ts      pure: group observation/decision/schedule/event by observation_id
  src/state/                one reducer plus selectors
  src/components/           Horizon, DeckBody, GestureRow, Chain, StatusBlocks, RecordingEdge,
                            SegmentReadout (ghost segments)
  src/styles/tokens.css     palette, type, space, motion tokens
  src/demo/fixtures.ts      realistic demo content; every fixture carries demo: true
  server/                   shells `dj <cmd> --json`, tails sessions/<id>/*.jsonl, serves build
```

**Adapter contract.** The UI never parses JSONL, never touches the filesystem, never builds a CLI
string. `client.ts` exposes exactly the actions in §8 and nothing more — if a capability is not
in the CLI there is no method for it, so the UI structurally *cannot* invent one (§13.10).
Nullable fields stay nullable to the component; no `?? 0` anywhere near a measurement. Types are
hand-written rather than generated so the mirror stays reviewable, plus a check that fails if the
Pydantic field set drifts.

## B.2 Persistent design contract in emitted markup

The design contract must survive in the shipped artifact, not only in this document.

- **Marker.** Emitted HTML carries `<!-- impeccable:product-schema 1 -->` and a
  `data-design-contract` attribute on the root naming this document and the committed direction.
- **Tokens are the only source of colour, type, spacing, and motion.** No literal colour or
  duration outside `tokens.css`; enforced by a lint rule that fails the build.
- **Semantic state attributes.** Every critical state from §9 is expressed as a `data-state`
  attribute (`on-air`, `preparing`, `pending`, `recording`, `offline`, `agent-absent`,
  `coverage-warning`, `coverage-critical`, `generation-failed`, `clock-uncertain`), so state is
  inspectable and testable in markup rather than inferred from styling.
- **Unavailability is explicit in markup.** Absent measurements render through `SegmentReadout`
  with `data-value="unavailable"` and an accessible label, never as a numeral.
- **Contract test.** A Vitest suite asserts the marker, the token discipline, and that every §9
  state has a distinct non-colour signal.

## B.3 Responsive demo mode

- Reachable at an explicit route; **never** the default view.
- Persistent, non-dismissable `DEMO DATA` marker in the viewport whenever fixtures are the source
  — not a subtle badge.
- Fixtures derived from real artifacts under `sessions/` (real prompts, real `goal`/`evidence`
  strings, real event shapes), timestamps shifted. No invented capability appears in any fixture.
- Must exercise every §9 critical state, including `clock_uncertain`, coverage warning and
  critical, generation failure, agent absent, and recording — a designed scenario walk, not a
  happy path.
- Must be driveable at desktop, tablet, and mobile breakpoints from the same route, so responsive
  behaviour is reviewable without a live runtime.

## B.4 Build and test commands

Run from `web/`. Node toolchain only; the Python environment is untouched.

```bash
npm install          # or pnpm install
npm run dev          # Vite dev server against a local dj runtime
npm run demo         # dev server forced into fixture-backed demo mode
npm run build        # typecheck + production build to web/dist
npm run preview      # serve the production build locally
npm run typecheck    # tsc --noEmit, strict
npm run lint         # eslint + the token-discipline rule
npm run test         # vitest run — adapter purity, contract, state rendering
npm run test:a11y    # keyboard traversal, focus order, live-region announcements
```

`npm run build` must fail on a type error, a lint violation, or a failing contract test. The
local server process is started separately and documented in `web/README.md` at implementation
time.

## B.5 Out of scope for Phase 2

No backend modification, no commits, no new Python dependency, no change to the CLI surface, no
capability not already exposed by `dj`, and no persistence of its own — the browser remains
non-authoritative (Platform §).
