import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { DESIGN_CONTRACT, DESIGN_CONTRACT_SEED, FINISH_LINE } from '../src/designContract'
import { FEEDBACK } from '../src/adapter/policy'
import { FEEDBACK_KINDS, FILTER_KINDS } from '../src/adapter/types'

// vitest runs with cwd = web/, so the repo root is one level up.
const REPO = resolve(process.cwd(), '..')
const read = (p: string) => readFileSync(join(REPO, p), 'utf8')

describe('design contract', () => {
  it('has all five parts, the seed, and the exact finish line', () => {
    expect(DESIGN_CONTRACT_SEED).toBe('6d715286')
    for (const part of [
      'TRUTH OVER SPECTACLE',
      'ABSENT IS NOT ZERO',
      'THE CLOCK CAN BE WRONG, AND SAYS SO',
      'THE BROWSER CANNOT BREAK THE MUSIC',
      'EVERY CRITICAL STATE HAS A NON-COLOUR SIGNAL',
    ]) {
      expect(DESIGN_CONTRACT).toContain(part)
    }
    expect(DESIGN_CONTRACT).toContain(
      'unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md',
    )
    expect(FINISH_LINE).toBe(
      'unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md',
    )
  })
})

describe('adapter mirrors the Python source', () => {
  it('FeedbackKind matches dj/observations.py exactly', () => {
    const py = read('dj/observations.py')
    for (const kind of FEEDBACK_KINDS) expect(py).toContain(`"${kind}"`)
    // No extra kinds invented on this side.
    const declared = [...py.matchAll(/^\s{4}[A-Z_]+ = "([a-z-]+)"$/gm)].map((m) => m[1])
    expect([...FEEDBACK_KINDS].sort()).toEqual(declared.sort())
  })

  it('policy preview table matches dj/policy.py bars and energy deltas', () => {
    const py = read('dj/policy.py')
    const expected: Record<string, [number, number]> = {
      love: [8.0, 0.05],
      dislike: [4.0, -0.05],
      'more-energy': [4.0, 0.2],
      'less-energy': [8.0, -0.2],
      boring: [4.0, 0.1],
      weird: [4.0, 0.05],
    }
    for (const f of FEEDBACK) {
      const [bars, delta] = expected[f.kind]!
      expect(f.bars, `${f.kind} bars`).toBe(bars)
      expect(f.energyDelta, `${f.kind} delta`).toBeCloseTo(delta, 5)
      // The goal string is quoted verbatim from the policy.
      expect(py).toContain(f.goal)
    }
  })

  it('offers only the filters the mixer actually implements', () => {
    const py = read('dj/mixer/supercollider.py')
    expect(py).toContain('"lowpass": "lowpass", "highpass": "highpass"')
    expect([...FILTER_KINDS]).toEqual(['lowpass', 'highpass'])
    // Specified but unbuilt effects must not appear as capability.
    const client = read('web/src/adapter/client.ts')
    for (const absent of ['delay', 'reverb', ' eq(']) {
      expect(client.toLowerCase()).not.toContain(absent)
    }
  })

  it('DJState field set matches dj/models.py', () => {
    const py = read('dj/models.py')
    for (const field of [
      'session_id', 'status', 'transport', 'decks', 'master', 'future', 'observations', 'updated_at',
    ]) {
      expect(py).toContain(field)
    }
    for (const field of ['peak_dbfs', 'lufs_short', 'limiter_reduction_db']) {
      expect(py).toContain(field)
    }
    for (const field of ['covered_until_bar', 'estimated_seconds']) {
      expect(py).toContain(field)
    }
  })

  it('the sentinel value matches what dj/runtime.py writes', () => {
    expect(read('dj/runtime.py')).toContain('86_400.0')
  })

  it('coverage thresholds match dj/config.py', () => {
    const py = read('dj/config.py')
    expect(py).toContain('normal_seconds: float = 90.0')
    expect(py).toContain('warning_seconds: float = 60.0')
    expect(py).toContain('critical_seconds: float = 30.0')
  })
})

describe('no capability beyond the CLI', () => {
  it('client exposes only actions the CLI implements', () => {
    const client = read('web/src/adapter/client.ts')
    const cli = read('dj/cli.py')
    for (const command of [
      'generate', 'play', 'crossfade', 'gain', 'filter', 'record', 'feedback', 'doctor',
    ]) {
      expect(cli).toContain(`def ${command}`)
      expect(client).toContain(`${command}(`)
    }
  })
})
