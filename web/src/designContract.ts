/**
 * The five-part design contract, emitted as the FIRST CHILD COMMENT of <body>.
 *
 * This is the persistent record of what this surface promises, travelling with the artifact
 * rather than living only in PRODUCT.md. Injected at build and dev time by the plugin in
 * vite.config.ts and asserted by tests/contract.test.ts.
 */

export const DESIGN_CONTRACT_SEED = '6d715286'

export const FINISH_LINE =
  'unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md'

export const DESIGN_CONTRACT = `
  Agent DJ — design contract
  impeccable:product-schema 1
  seed 6d715286

  1. TRUTH OVER SPECTACLE.
     Every value shown is traceable to an artifact the system writes: sessions/<id>/state.json,
     observations.jsonl, decisions.jsonl, schedules.jsonl, events.jsonl. No fabricated metric,
     no fake audio visualisation, no invented capability. If dj does not expose it, this surface
     does not offer it. Lowpass and highpass exist; delay, reverb and EQ do not.

  2. ABSENT IS NOT ZERO.
     Unavailable measurements render as unlit ghost segments with data-value="unavailable",
     never as a numeral. master.peak_dbfs and master.lufs_short are null in every recorded
     session. future.estimated_seconds = 86400 is a sentinel meaning indefinite and renders as
     SAFE, never as a duration. deck energy is agent-maintained intent, never described as
     measured.

  3. THE CLOCK CAN BE WRONG, AND SAYS SO.
     The musical bar is derived from (started_at, bpm) and the reader's local clock, with no
     heartbeat and no drift correction. Three defects are confirmed in recorded data. When the
     clock cannot be trusted, every derived value withdraws its claim (data-state="clock-uncertain")
     rather than showing a plausible wrong number. Stored values keep displaying, because they
     remain true. This is not an error: music is unaffected.

  4. THE BROWSER CANNOT BREAK THE MUSIC.
     Control and observation only. No audio work, no scheduling audio correctness depends on,
     no system state of record. Closing this tab does not affect the set. When the local control
     server is absent this surface fails honestly and never falls back to fixtures; demo mode is
     an explicit, permanently marked source.

  5. EVERY CRITICAL STATE HAS A NON-COLOUR SIGNAL.
     offline, agent-absent, preparing, pending, recording, coverage-warning, coverage-critical,
     generation-failed, clock-uncertain and on-air each carry a data-state attribute and a
     distinct shape or position, never colour alone. Motion is reserved for what is actually
     moving in the music; prefers-reduced-motion is a real alternate mode.

  ${FINISH_LINE}
`
