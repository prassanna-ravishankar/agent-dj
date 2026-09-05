<!-- impeccable:product-schema 1 -->

# Agent DJ web — handoff

Frontend is complete and self-contained under `web/`. The **Python integration server is not
built** — that is the work described in §4 below, owned by Codex.

Nothing outside `web/` was modified. Nothing was committed.

---

## 1. Commands

Run from `web/`. Node toolchain only; the Python environment is untouched.

```bash
npm install        # once

npm run demo       # fixture-backed dev server — no runtime needed
npm run dev        # dev server against a live local control server
npm run build      # tsc --noEmit && vite build -> web/dist
npm run preview    # serve the production build
npm run typecheck  # tsc --noEmit, strict
npm run lint       # eslint + token-discipline check
npm run test       # vitest run (41 tests)
npm run test:a11y  # keyboard, focus, live-region subset
npm run shots      # capture screenshots/ from the production build
```

`npm run build` fails on a type error, a lint violation, or a failing contract test.

Current status: typecheck clean, lint clean, 41/41 tests passing, production build succeeds
(191 kB JS / 62 kB gzip, 31 kB CSS / 6 kB gzip).

---

## 2. Routes

| Route | Purpose |
|---|---|
| `/` | Performance console — horizon, decks, controls, gestures, chain |
| `/?demo=true` | Same, backed by fixtures. Permanently marked **DEMO DATA** |
| `/?demo=true&scenario=<id>` | A specific scenario (see §5) |

The **Pre-set** view (doctor, process control, generation prompting) is an in-page view toggle,
not a separate URL. Two views total; no router library.

`npm run demo` sets demo mode as the default for every route.

---

## 3. Adapter contract

The browser talks to exactly one module, `src/adapter/client.ts`. It never parses JSONL, never
touches the filesystem, never builds a CLI string. Base path `/api`.

### Request / response

Every response is JSON. Non-2xx is treated as a command rejection; `409` maps to `refused`,
`400` to `invalid`, anything else to `transport`. `204` is a valid empty success.

| Method | Endpoint | Body | Returns | CLI it wraps |
|---|---|---|---|---|
| `GET` | `/api/snapshot` | — | `Snapshot` | `dj state --json` + logs (see below) |
| `GET` | `/api/doctor` | — | `DoctorReport` | `dj doctor --json` |
| `POST` | `/api/runtime/start` | `{test_mode: bool}` | `ProcessHealth` | `dj start [--test-mode] --json` |
| `POST` | `/api/runtime/stop` | — | `ProcessHealth` | `dj stop --json` |
| `POST` | `/api/agent/start` | `{test_mode: bool}` | `ProcessHealth` | `dj agent start --json` |
| `POST` | `/api/agent/stop` | — | `ProcessHealth` | `dj agent stop --json` |
| `POST` | `/api/agent/prepare-next` | `{direction?: string, duration: number}` | one-shot preparation result | `dj agent prepare-next ... --json` |
| `POST` | `/api/generate` | `{deck, prompt, bpm, duration}` | `204` | `dj generate <deck> --prompt … --bpm … --duration …` |
| `POST` | `/api/play` | `{deck}` | `204` | `dj play <deck> --json` |
| `POST` | `/api/crossfade` | `{target, bars}` | `204` | `dj crossfade <target> --bars <n> --json` |
| `POST` | `/api/gain` | `{deck, gain_db}` | `204` | `dj gain <deck> <db> --json` |
| `POST` | `/api/filter` | `{deck, kind, frequency_hz}` | `204` | `dj filter <deck> <kind> <hz> --json` |
| `POST` | `/api/record` | `{action: "start"\|"stop"}` | `204` | `dj record <action> --json` |
| `POST` | `/api/feedback` | `{kind}` | `204` | `dj feedback <kind> --json` |

`kind` is one of `love`, `dislike`, `more-energy`, `less-energy`, `boring`, `weird`.
`filter.kind` is `lowpass` or `highpass` **only** — the mixer raises on anything else.

### `Snapshot`

The one payload the console renders. Assembled server-side; the browser does no log parsing.

```jsonc
{
  "state":     { /* DJState, verbatim from sessions/<id>/state.json */ },
  "runtime":   { "ok": bool, "running": bool, "pid": int|null, "local_only": true },
  "agent":     { /* same shape */ },
  "events":    [ /* events.jsonl, parsed, chronological */ ],
  "decisions": [ /* decisions.jsonl -> the inner `decision` object of each record */ ],
  "schedules": [ /* schedules.jsonl, parsed */ ],
  "demo":      false
}
```

Notes that matter:

- `decisions` must carry the **inner** `decision` object (`observation_id`, `goal`, `evidence`,
  `target_deck`, `prompt`, `transition_bars`, `energy_delta`), not the outer event wrapper.
- Send `state` **verbatim**. Do not normalise nulls, do not convert the `86_400` sentinel, do
  not fill in `transport.bar`. The surface depends on receiving the raw truth.
- `events` may be capped (last ~500 is ample); the chain joins on `observation_id`.

### Events stream

`GET /api/events` — `text/event-stream`. Any message body triggers a snapshot re-read; the
payload is ignored, so a bare `data: changed\n\n` is sufficient. Emit on state/log change, or on
a short poll. The client reconnects on its own and stays silent when the stream is absent.

### Error shape

```jsonc
{ "detail": "human-readable reason" }   // or { "error": "..." }
```

Surfaced inline to the performer. Refusals are expected and normal (`dj session-new` refuses
while the runtime is up; `dj start` refuses without a prepared deck) — return `409` with the
reason and the UI states it plainly.

---

## 4. What Codex must build

**A local HTTP server implementing §3.** Suggested `web/server/` (FastAPI or Starlette).

1. **Serve** `web/dist/` as static files.
2. **Snapshot assembly** — read `sessions/.current`, then that session's `state.json`,
   `events.jsonl`, `decisions.jsonl`, `schedules.jsonl`; probe runtime and agent health.
   Prefer importing `dj.session.SessionStore`, `dj.runtime.RuntimeController`, and
   `dj.agent.AgentController` directly over shelling out for reads.
3. **Command endpoints** — shell `uv run dj … --json` (or call the same code paths). Map a
   `typer.BadParameter` / refusal to `409` with its message.
4. **SSE** at `/api/events` — watch the session directory, emit on change.
5. **Bind to localhost only.** No external interface, no auth, no CORS beyond same-origin.

### Boundaries to preserve

- **Never** put the server on the audio path. It shells commands and reads files; nothing more.
- **Never** normalise `state.json` on the way out (see §3 notes).
- The server must be killable mid-set with no audio consequence — same guarantee the CLI and
  the agent already have.
- Do not add capability the CLI lacks. The UI has no method for it and the contract test fails
  if one appears.

---

## 5. Demo scenarios

`?scenario=<id>`. Every fixture is derived from real artifacts under `sessions/` — real prompts,
real `goal`/`evidence` strings, real event shapes — with timestamps shifted.

| id | Exercises |
|---|---|
| `live-safe` | On air, `SAFE` sentinel, one intent in flight, full chain |
| `coverage-warning` | Under 60 s; ember falloff |
| `coverage-critical` | Under 30 s; red falloff, preparing deck, assertive announcement |
| `agent-absent` | Survivable degraded state, stated calmly |
| `generation-failed` | Deck B failed, deck A continues, transition cancelled |
| `clock-uncertain` | Defect 1 reproduced; derived bar withdrawn to ghost cells |
| `recording` | Persistent red top edge |
| `offline` | Runtime down; horizon replaced by a plain statement |
| `empty` | Fresh session; empty states, not zeros |

---

## 6. Known gaps

1. **No integration server** — the whole of §4. Live methods currently fail with `unavailable`
   and say so honestly.
2. **Master metering is permanently ghosted.** `peak_dbfs` / `lufs_short` are `null` in every
   recorded session. When metering is wired into `MasterState`, the readouts light up with no
   frontend change.
3. **The clock defects are upstream.** `PRODUCT.md` §5 documents three, confirmed across all 14
   sessions: `started_at` later than `updated_at` (11/14), `stopped` retaining `started_at`
   (13/14), `transport.bar` never written (14/14). `clock_uncertain` handles them honestly but
   **does not fix them** — the durable fix is in `dj/runtime.py` (null `started_at` on stop;
   write `updated_at` after the transport fields) and is deliberately out of frontend scope.
4. **Horizon range may be degenerate in practice.** `estimated_seconds` is the sentinel almost
   always, so the interesting 30–90 s band may rarely appear. Wants validation against a real
   Magenta-backed session.
5. **`covered_until_bar` is `0`** in most recorded artifacts, so the horizon leans on
   `estimated_seconds`. If that field starts being maintained, the falloff can use it directly.
6. **The policy mirror can drift.** `src/adapter/policy.ts` duplicates `dj/policy.py` for
   preview only. `tests/contract.test.ts` pins bars, deltas, and goal strings; if Python
   changes, the test fails first.
7. **No booth-hardware check.** Grain over large dark fields can band on some projectors and
   OLED panels. Untested on real hardware.
8. **Reduced-motion tested by media query, not by device.** The alternate mode (horizon steps
   per bar instead of scrolling) is implemented but has not been observed on a real machine
   with the OS setting on.

---

## 7. File map

```
web/
  src/adapter/     types.ts client.ts clock.ts coverage.ts policy.ts chain.ts
  src/state/       store.ts selectors.ts
  src/components/  Horizon Decks GestureRow Chain Controls TopEdge SegmentReadout ShortcutOverlay
  src/pages/       Prepare
  src/styles/      tokens.css base.css
  src/demo/        fixtures.ts
  src/designContract.ts
  scripts/         check-tokens.mjs shots.mjs
  tests/           clock coverage contract states a11y
  screenshots/     11 review captures
```

`tokens.css` is the only source of colour, type, spacing, and motion; `scripts/check-tokens.mjs`
fails the build on any literal elsewhere.
