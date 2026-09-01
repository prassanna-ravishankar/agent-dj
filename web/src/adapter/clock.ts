/**
 * Pure musical-clock derivation, mirroring dj/scheduler.py current_bar() and dj/transport.py.
 *
 * The bar is DERIVED, never stored: nothing writes transport.bar during a set. Every bar
 * number shown is an inference from (started_at, bpm) plus the reader's local clock, with no
 * heartbeat and no drift correction against the audio clock.
 *
 * PRODUCT.md 5 documents three defects confirmed in all 14 recorded sessions:
 *   1. started_at later than updated_at (11/14, skew 2.8s..135.9s)
 *   2. status "stopped" with started_at still populated (13/14)
 *   3. transport.bar is 0 everywhere and never written
 *
 * When the clock cannot be trusted the surface must WITHDRAW the claim rather than show a
 * plausible wrong number.
 */

import type { DJState } from './types'

/** dj/cli.py generate --bpm min=40 max=240. */
export const BPM_MIN = 40
export const BPM_MAX = 240

/** started_at may legitimately trail updated_at by a moment; beyond this it is incoherent. */
export const FUTURE_START_TOLERANCE_MS = 1_000

/** How long a "live" state may go unwritten before we stop trusting derived time. */
export const STALE_STATE_MS = 30_000

export const BEATS_PER_BAR = 4

export type ClockUncertainReason =
  | 'future_start'
  | 'contradiction'
  | 'stale_state'
  | 'stopped_but_timestamped'
  | 'implausible_tempo'
  | 'reader_clock_skew'

export const CLOCK_REASON_TEXT: Record<ClockUncertainReason, string> = {
  future_start: 'Transport start time is later than the last state write.',
  contradiction: 'Runtime status and transport playing flag disagree.',
  stale_state: 'State file has not been written recently while marked live.',
  stopped_but_timestamped: 'Transport is stopped but still carries a start time.',
  implausible_tempo: 'Tempo is outside the accepted 40-240 BPM range.',
  reader_clock_skew: 'This machine’s clock is behind the last state write.',
}

export interface MusicalClock {
  /** null whenever the bar position cannot be honestly claimed. */
  bar: number | null
  beat: number | null
  secondsPerBar: number
  bpm: number
  uncertain: boolean
  reasons: ClockUncertainReason[]
  /** True when the transport is genuinely advancing (playing and trustworthy). */
  advancing: boolean
}

export function secondsPerBar(bpm: number): number {
  return (60 / bpm) * BEATS_PER_BAR
}

export function barsToSeconds(bars: number, bpm: number): number {
  return bars * secondsPerBar(bpm)
}

/** dj/transport.py next_phrase_bar — ceil to the next phrase multiple. */
export function nextPhraseBar(currentBar: number, phraseBars = 4): number {
  if (phraseBars <= 0) throw new Error('phraseBars must be positive')
  return Math.ceil((currentBar + 1e-9) / phraseBars) * phraseBars
}

function parse(iso: string | null): number | null {
  if (!iso) return null
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? null : ms
}

/**
 * Derive the musical clock and its trustworthiness.
 *
 * @param state canonical DJState
 * @param now reader's wall clock, injected for determinism in tests
 */
export function deriveClock(state: DJState, now: number = Date.now()): MusicalClock {
  const { transport, status } = state
  const bpm = transport.bpm
  const reasons: ClockUncertainReason[] = []

  const startedAt = parse(transport.started_at)
  const updatedAt = parse(state.updated_at)

  // Trigger: implausible tempo. Guarded first — every other derivation divides by it.
  const tempoValid = Number.isFinite(bpm) && bpm >= BPM_MIN && bpm <= BPM_MAX
  if (!tempoValid) reasons.push('implausible_tempo')

  // Trigger: future start. Defect 1 — 11/14 recorded sessions.
  if (startedAt !== null && updatedAt !== null && startedAt - updatedAt > FUTURE_START_TOLERANCE_MS) {
    reasons.push('future_start')
  }

  // Trigger: contradiction between runtime status and transport flag.
  if ((status === 'live') !== transport.playing) reasons.push('contradiction')
  if (transport.playing && startedAt === null) {
    if (!reasons.includes('contradiction')) reasons.push('contradiction')
  }

  // Trigger: stale state while live.
  if (status === 'live' && updatedAt !== null && now - updatedAt > STALE_STATE_MS) {
    reasons.push('stale_state')
  }

  // Trigger: reader clock skew.
  if (updatedAt !== null && now < updatedAt - FUTURE_START_TOLERANCE_MS) {
    reasons.push('reader_clock_skew')
  }

  // Trigger: stopped but timestamped. Defect 2 — 13/14 recorded sessions.
  // Only material when elapsed time would actually be derived, i.e. someone might mistake the
  // retained timestamp for evidence of playback.
  const stoppedButTimestamped = !transport.playing && startedAt !== null
  if (stoppedButTimestamped && status === 'live') {
    if (!reasons.includes('stopped_but_timestamped')) reasons.push('stopped_but_timestamped')
  }

  const uncertain = reasons.length > 0

  // Mirrors current_bar(): not playing -> the stored bar, which is 0 in every recorded session.
  if (!transport.playing || startedAt === null) {
    return {
      bar: uncertain ? null : transport.bar,
      beat: uncertain ? null : 0,
      secondsPerBar: tempoValid ? secondsPerBar(bpm) : Number.NaN,
      bpm,
      uncertain,
      reasons,
      advancing: false,
    }
  }

  if (uncertain) {
    return {
      bar: null,
      beat: null,
      secondsPerBar: tempoValid ? secondsPerBar(bpm) : Number.NaN,
      bpm,
      uncertain: true,
      reasons,
      advancing: false,
    }
  }

  const spb = secondsPerBar(bpm)
  const elapsedSeconds = (now - startedAt) / 1000
  const exactBar = elapsedSeconds / spb

  // Elapsed time must not run backwards.
  if (exactBar < 0) {
    return {
      bar: null,
      beat: null,
      secondsPerBar: spb,
      bpm,
      uncertain: true,
      reasons: ['reader_clock_skew'],
      advancing: false,
    }
  }

  return {
    bar: exactBar,
    beat: (exactBar % 1) * BEATS_PER_BAR,
    secondsPerBar: spb,
    bpm,
    uncertain: false,
    reasons: [],
    advancing: true,
  }
}

/** Whole-bar display value, or null when the claim must be withdrawn. */
export function displayBar(clock: MusicalClock): number | null {
  return clock.bar === null ? null : Math.floor(clock.bar)
}

/** Bars remaining until a scheduled bar, or null when the clock cannot support the claim. */
export function barsUntil(clock: MusicalClock, atBar: number): number | null {
  if (clock.bar === null) return null
  return atBar - clock.bar
}
