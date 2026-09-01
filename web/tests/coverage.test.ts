import { describe, expect, it } from 'vitest'
import { COVERAGE_THRESHOLDS, deriveCoverage, SAFE_SENTINEL_SECONDS } from '../src/adapter/coverage'

describe('coverage', () => {
  it('renders the 86400 sentinel as SAFE with no duration', () => {
    const c = deriveCoverage({ covered_until_bar: 0, estimated_seconds: SAFE_SENTINEL_SECONDS })
    expect(c.level).toBe('safe')
    expect(c.sentinel).toBe(true)
    // The critical assertion: never expose the sentinel as a number to render.
    expect(c.seconds).toBeNull()
  })

  it('maps the configured thresholds', () => {
    expect(deriveCoverage({ covered_until_bar: 0, estimated_seconds: 120 }).level).toBe('normal')
    expect(deriveCoverage({ covered_until_bar: 0, estimated_seconds: COVERAGE_THRESHOLDS.normal }).level).toBe('normal')
    expect(deriveCoverage({ covered_until_bar: 0, estimated_seconds: 47 }).level).toBe('warning')
    expect(deriveCoverage({ covered_until_bar: 0, estimated_seconds: 18 }).level).toBe('critical')
    expect(deriveCoverage({ covered_until_bar: 0, estimated_seconds: 0 }).level).toBe('critical')
  })
})
