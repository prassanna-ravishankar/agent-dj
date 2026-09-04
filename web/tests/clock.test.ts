import { describe, expect, it } from 'vitest'
import { deriveClock, displayBar, nextPhraseBar, secondsPerBar } from '../src/adapter/clock'
import { buildScenario } from '../src/demo/fixtures'
import type { DJState } from '../src/adapter/types'

const NOW = Date.parse('2026-09-01T12:00:00.000Z')

function state(overrides: Partial<DJState['transport']>, extra: Partial<DJState> = {}): DJState {
  return {
    session_id: 's',
    status: 'live',
    transport: {
      playing: true,
      bpm: 124,
      bar: 0,
      beat: 0,
      started_at: new Date(NOW - 60_000).toISOString(),
      sample_position: 0,
      ...overrides,
    },
    decks: {
      A: { name: 'A', status: 'playing', source: 'magenta', prompt: null, gain_db: 0, energy: null, audio_path: null, duration_seconds: null },
      B: { name: 'B', status: 'prepared', source: 'magenta', prompt: null, gain_db: -60, energy: null, audio_path: null, duration_seconds: null },
    },
    master: { peak_dbfs: null, lufs_short: null, limiter_reduction_db: 0 },
    future: { covered_until_bar: 0, estimated_seconds: 86_400 },
    observations: [],
    // A live runtime writes state often; keep this inside the staleness window.
    updated_at: new Date(NOW - 5_000).toISOString(),
    ...extra,
    stream: extra.stream ?? {
      available: false,
      enabled: false,
      healthy: false,
      fallback_active: true,
      stream_active: false,
      warming_up: false,
      signal_detected: false,
      phase: 'disabled',
      force_fallback: false,
      signal_level: null,
      mix: 0,
      temperature: 1,
      top_k: 40,
      prompts: [],
    },
    codex: extra.codex ?? { thread_id: null, turn_id: null, turn_status: 'detached' },
  }
}

describe('musical clock', () => {
  it('derives bars from elapsed time, mirroring current_bar()', () => {
    const clock = deriveClock(state({}), NOW)
    expect(clock.uncertain).toBe(false)
    expect(clock.bar).toBeCloseTo(60 / secondsPerBar(124), 5)
    expect(clock.advancing).toBe(true)
  })

  it('DEFECT 1: withdraws the bar when started_at is later than updated_at', () => {
    const s = state({ started_at: new Date(NOW - 1_000).toISOString() }, {
      updated_at: new Date(NOW - 90_000).toISOString(),
    })
    const clock = deriveClock(s, NOW)
    expect(clock.uncertain).toBe(true)
    expect(clock.reasons).toContain('future_start')
    expect(clock.bar).toBeNull()
    expect(displayBar(clock)).toBeNull()
  })

  it('DEFECT 2: flags a stopped session that still carries started_at', () => {
    const s = state({ playing: false })
    const clock = deriveClock(s, NOW)
    // status "live" while playing is false is itself a contradiction.
    expect(clock.uncertain).toBe(true)
    expect(clock.bar).toBeNull()
  })

  it('a genuinely stopped session is NOT uncertain and does not derive elapsed time', () => {
    const s = state({ playing: false }, { status: 'stopped' })
    const clock = deriveClock(s, NOW)
    expect(clock.uncertain).toBe(false)
    expect(clock.advancing).toBe(false)
    expect(clock.bar).toBe(0)
  })

  it('flags implausible tempo', () => {
    expect(deriveClock(state({ bpm: 5 }), NOW).reasons).toContain('implausible_tempo')
    expect(deriveClock(state({ bpm: 900 }), NOW).reasons).toContain('implausible_tempo')
  })

  it('flags stale state while live', () => {
    const s = state({}, { updated_at: new Date(NOW - 120_000).toISOString() })
    expect(deriveClock(s, NOW).reasons).toContain('stale_state')
  })

  it('flags reader clock skew', () => {
    const s = state({}, { updated_at: new Date(NOW + 60_000).toISOString() })
    expect(deriveClock(s, NOW).reasons).toContain('reader_clock_skew')
  })

  it('flags playing with no start time as a contradiction', () => {
    const clock = deriveClock(state({ started_at: null }), NOW)
    expect(clock.reasons).toContain('contradiction')
    expect(clock.bar).toBeNull()
  })

  it('never returns a bar when uncertain', () => {
    for (const id of ['clock-uncertain'] as const) {
      const snap = buildScenario(id, NOW)
      const clock = deriveClock(snap.state, NOW)
      expect(clock.uncertain).toBe(true)
      expect(clock.bar).toBeNull()
    }
  })

  it('nextPhraseBar rounds up to the phrase boundary', () => {
    expect(nextPhraseBar(184, 4)).toBe(188)
    expect(nextPhraseBar(184.2, 4)).toBe(188)
    expect(nextPhraseBar(0, 4)).toBe(4)
  })
})
