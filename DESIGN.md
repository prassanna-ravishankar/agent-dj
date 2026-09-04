<!-- impeccable:product-schema 1 -->

# Agent DJ — design record

Written from the implemented system, not from intent. Every claim is checkable against `web/`
or a screenshot in `web/screenshots/`.

`PRODUCT.md` holds product truth and the committed language. This documents what was actually
built, what changed during the build, and what remains open.

---

## 1. The direction

**The Horizon.** Composition organised around the coverage margin as literal space: the left
edge is **now** — on air, guaranteed — and rightward is the future the system has bought
itself. Bars are the horizontal unit, so phrase-aligned latency reads as *distance* rather than
delay.

The mechanism it exists to express: *a generative music system whose creative loop is
deliberately severed from its audio loop, so the set can be surprised, degraded, or abandoned by
its own intelligence without the music ever stopping.*

Three probes shaped the final composition:

| Probe | Taken | Rejected |
|---|---|---|
| A — panoramic horizon | Topology: NOW-to-future spatial read, asymmetric decks, gesture row, narrow chain rail | — |
| B — deck seam | The phrase-boundary seam as the crossfade preview | Its process-step footer (OBSERVE/FOCUS/PREPARE/COMMIT/EXECUTE/EVALUATE) — a workflow the system does not have |
| C — causal entity | Observation → Decision → Generation → Schedule as one entity accruing stages; intent travelling to its landing bar | Its fabricated metric density, fake readouts, and heavy paneling |

## 2. Grammar fused from the challenger hand

Three concept seeds were weighed on audience identification and product clarity. Two
contributed; one was rejected on record.

**Seven-segment — the strongest contribution.** The unlit ghost segment solved a problem the
design already had. Master loudness is genuinely unavailable (`peak_dbfs` and `lufs_short` are
`null` in every recorded session), and a ghost cell shows *this cell exists and its value is
absent* without inventing a zero. It became: the standard rendering for every unavailable
measurement; fixed non-reflowing numeric cells throughout; and the display for
`clock_uncertain`, where the bar counter shows unlit cells — visibly present, visibly not
asserting a value.

**Cassette-futurist — one idea, not the idiom.** Every feedback control permanently prints its
own consequence (`MORE ENERGY · 4 bars · +0.20`), so the performer never has to recall the
policy table. The full fascia was rejected: a fascia asserts "this panel *is* the machine", and
the browser explicitly is not.

**Miura — rejected outright.** Linked crease geometry implies coupling that does not exist.
Decks are independent; a gesture prepares the off-air deck and schedules exactly one crossfade.
Nothing propagates. It would have been beautiful and a lie about the mechanism.

## 3. What the surface refuses to do

The design is mostly defined by what it will not show.

| Refusal | Why | Where |
|---|---|---|
| No fake audio visualisation | No audio reaches the browser. A waveform would be decoration pretending to be a measurement; prompt gravity may visualise real lane weights, never imply audio amplitude | absent throughout; `MorphField` |
| `86_400` never renders as a duration | It is a sentinel for *indefinite* because JSON cannot hold infinity | `coverage.ts`, renders **SAFE** |
| Null loudness never renders as `0` | Metering is specified but not wired into state | `SegmentReadout`, ghost cells |
| Energy never described as measured | It is agent-maintained intent via `energy_delta` | labelled `ENERGY (INTENT)` |
| No delay, reverb, or EQ | The mixer raises on anything but lowpass/highpass | `FILTER_KINDS` |
| No fallback bar number | The clock is derived and uncorrected | `clock.ts` returns `null` |
| No fixture fallback on a live failure | Demo mode is an explicit, marked source | `client.ts` fails with `unavailable` |
| No capability the CLI lacks | The client has no method for it | contract test |

## 4. Critical states

Ten states, each with a `data-state` attribute and a **distinct shape or position** — never
colour alone, because the room is dark and colour vision varies.

| State | Non-colour signal |
|---|---|
| on-air | Solid left-edge marker + the only emissive surface; deck body ~1.6× wider |
| prepared | No marker, no emission, cold slate |
| preparing | Horizontal indeterminate fill, never a spinner |
| pending | Dotted stem on the horizon at the target bar, counting down in bars |
| recording | Persistent red hairline across the **full** top edge of the viewport |
| offline | Struck-through square; horizon replaced by a plain statement |
| agent-absent | Horizontal bar mark; calm sentence, not an error colour |
| coverage-warning | Falloff visibly pulled toward now |
| coverage-critical | Falloff collapsed to now; bold uppercase directive |
| generation-failed | Diagonal cross; dashed deck marker |
| clock-uncertain | Hollow square; ghost cells in every derived readout |

## 5. Clock integrity

The single most consequential finding of the whole build, and it came from evidence rather than
design reasoning.

The musical bar is **derived, never stored**. `current_bar()` computes it from
`(started_at, bpm)` and the reader's local clock. Nothing writes `transport.bar` during a set;
there is no heartbeat and no drift correction. Measured across all 14 recorded sessions:

| # | Defect | Extent |
|---|---|---|
| 1 | `started_at` later than `updated_at` | 11/14, skew 2.8 s – 135.9 s |
| 2 | `stopped` while `started_at` remains populated | 13/14 |
| 3 | `transport.bar` is `0` and never written | 14/14 |

Defect 2 is the dangerous one: a naive reader deriving elapsed time from a stopped session gets
a bar number growing forever on a system producing no audio.

Because the design makes bars the primary spatial unit, a wrong clock corrupts the central
metaphor. `clock_uncertain` (six triggers, `adapter/clock.ts`) is the answer: **derived** values
withdraw their claim; **stored** values keep displaying, because they remain true. See
`screenshots/clock-uncertain-desktop.png` — the bar shows `8888` ghost cells and names its
reason, while `SAFE`, deck status, prompts, and the chain all continue normally.

This is explicitly **not** an error state. Audio never depended on this clock.

The defects are upstream and were **not** fixed here — that would mean editing `dj/runtime.py`,
outside the frontend boundary. `web/HANDOFF.md` §6.3 records the durable fix.

## 6. Signature interaction — "commit to the bar"

Press a feedback key. Instead of a toast, the consequence is drawn onto the horizon as a ghost
tick at the phrase-aligned bar where it will land, its width the policy's transition length,
with the deck seam previewing the swap. It is visibly *a thing placed in the future*, not a
button that fired. As bars advance the tick travels left toward now; on execution it solidifies
and the decks swap.

The performer learns the system's patience by watching their own intent travel. That is the
product in one gesture: **you influence the future, the present stays guaranteed.**

Two structural facts the surface makes visible:

- **Feedback always targets the off-air deck.** It is never an edit to what you are hearing.
- **Approval is the slowest gesture.** `love` and `less-energy` take 8 bars; everything
  disruptive takes 4. The system is more patient when asked to keep going — consistent with
  `SOUL.md`: "If something works, allow it to work."

### Control Room — a personal instrument

The Control Room is composed as an instrument, not a SaaS settings page. **Play** is the default
performance surface, **Shape** holds precise prompt and scheduling controls, and **Codex** remains
a clearly subordinate project collaborator outside the audio path. Do not flatten the three into
co-equal dashboard columns or lead with configuration.

Prompt gravity is a control map, not an audio visualiser: node emphasis and the field centroid are
calculated from the lane weights the performer is controlling. It must never become a decorative
waveform, spectrum, or other claim about audio the browser does not receive.

## 7. Language

**Palette — one light source.** Warm near-black ground (`#0E0D0C`, brown-leaning, never blue)
with a single amber-white emissive that only ever means on-air/guaranteed. Cold slate for
prepared-but-silent (the −60 dB truth). Ember for warning. One high-chroma red, reserved
exclusively for critical coverage and recording. Exactly one gradient exists in the design: the
coverage falloff.

**Type.** Inter Tight for labels and prose; JetBrains Mono for every number a performer compares
over time. Fixed cells, tabular numerals — digits never reflow.

**Material — lit panel, not floating card.** Flush surfaces, 1px hairlines, small luminance
steps. No drop shadows, no rounded floating rectangles. Depth from light falloff, not elevation.
One texture: low-opacity SVG fractal grain so large dark fields do not band on booth projectors.

**Motion — only what is actually moving in the music.** The bar advances; the horizon scrolls at
transport rate. Nothing else animates. Under `prefers-reduced-motion` the horizon stops
scrolling and steps once per bar — a real alternate mode, not durations zeroed.

**Terminology.** "On air", "covered until", "lands in N bars", "prepared". `goal` and `evidence`
quoted verbatim from `decisions.jsonl`.

## 8. Responsive

**Desktop (≥1280px)** — single non-scrolling viewport: horizon, decks, controls, gestures, plus
a persistent chain rail. Decks absorb vertical slack but cap at 22rem so nothing stretches into
emptiness.

**Tablet** — same stack, chain moves below.

**Mobile (≤640px)** — genuinely redesigned, not shrunk. Priority order answers *is it playing,
am I safe, did my gesture land* with zero scrolling: bar and SAFE first, on-air deck, incoming
transition, then a 2×3 thumb grid of gestures. Filter and master metering are demoted; the
horizon band survives but its ruler and travelling ticks are dropped as unreadable at that size.
In the Control Room, the desktop prompt constellation likewise becomes a 2×3 tactile direction
bank: preserve the same weighted choices, but remove the centroid rings and spatial geometry that
do not survive at thumb scale.

**Keyboard throughout** — `1`–`6` feedback, `A`/`B` deck focus, `Space` play, `C` crossfade,
`R` record (confirmed), `/` chain, `?` reference. Visible focus rings, logical tab order, ARIA
live regions **polite** by default, **assertive** only for critical coverage and generation
failure.

## 9. What the build changed

Four things the implementation corrected against the Phase-1 design:

1. **Ghost segments leaked into present values.** Painting ghosts in unused leading cells made
   `184` read as "8184" and `0 dB` as "880". Caught by inspecting the first screenshot. A ghost
   now paints only when the *whole* readout is absent — which is what it means.
2. **Ghosts were text content.** The `8` glyphs sat in `textContent`, so raw text extraction saw
   `8888` for an absent value. Caught by a test assertion. Now drawn via CSS `content`, so they
   never enter the accessibility tree.
3. **Mobile priority was wrong.** The first mobile render put deck detail above coverage,
   contradicting `PRODUCT.md` §9. Reordered so coverage leads.
4. **The token lint caught three of my own violations** — two literal `rgba()` and one literal
   `1.6s`. Fixed by adding `--amber-body`, `--scrim`, and `--dur-sweep` rather than exempting
   them.

## 10. Verification

```
typecheck   tsc --noEmit, strict            clean
lint        eslint + token discipline       clean
test        vitest                          41/41 passing
build       tsc && vite build               191 kB JS (62 kB gz), 31 kB CSS (6 kB gz)
screenshots 11 captures, desktop/tablet/mobile
```

Test coverage is weighted toward the honesty guarantees, since those are what a UI most easily
breaks: the sentinel never rendering as a duration; absent never rendering as zero; zero
rendering as zero; the clock withdrawing under all six triggers; every critical state carrying
its attribute; the policy mirror pinned against `dj/policy.py`; and the client exposing no
capability the CLI lacks.

## 11. Open

1. **No integration server.** Owned by Codex; contract in `web/HANDOFF.md` §3–4.
2. **Clock defects are upstream** and unfixed by design (§5).
3. **Horizon range may be degenerate** — the sentinel dominates recorded data, so the
   interesting 30–90 s band may be rare. Needs a real Magenta-backed session.
4. **Booth hardware untested** — grain banding on projectors and OLED.
5. **Reduced motion verified by media query, not on a real machine** with the OS setting on.
6. **`PROJECT_SPEC.md:3059` — "do not build a web UI"** — read as scoped to the Milestone 0/1
   bootstrap prompt (§85), alongside "do not add an LLM SDK" and "do not add Magenta yet", both
   already superseded. Recorded in `PRODUCT.md` §Platform rather than worked around silently. If
   read as permanent, this build should not ship.

---

*unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict,
and DESIGN.md*
