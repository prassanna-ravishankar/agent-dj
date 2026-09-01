/**
 * Pure coverage derivation. Mirrors dj/config.py CoverageConfig and PROJECT_SPEC.md 17.
 */

import type { FutureState } from './types'

/** dj/runtime.py writes 86_400 as "indefinite" because JSON cannot represent infinity. */
export const SAFE_SENTINEL_SECONDS = 86_400

export const COVERAGE_THRESHOLDS = {
  normal: 90,
  warning: 60,
  critical: 30,
} as const

export type CoverageLevel = 'safe' | 'normal' | 'warning' | 'critical'

export interface Coverage {
  level: CoverageLevel
  /** null when the sentinel is present — there is no meaningful duration to show. */
  seconds: number | null
  /** True when estimated_seconds is the indefinite sentinel. */
  sentinel: boolean
  coveredUntilBar: number
}

/**
 * `safe` means a looping buffer guarantees audio indefinitely — it is a STATE, never a
 * duration. Rendering the sentinel as "24 hours" would be a lie (PRODUCT.md 13.5).
 */
export function deriveCoverage(future: FutureState): Coverage {
  const seconds = future.estimated_seconds
  if (seconds >= SAFE_SENTINEL_SECONDS) {
    return { level: 'safe', seconds: null, sentinel: true, coveredUntilBar: future.covered_until_bar }
  }
  let level: CoverageLevel
  if (seconds < COVERAGE_THRESHOLDS.critical) level = 'critical'
  else if (seconds < COVERAGE_THRESHOLDS.warning) level = 'warning'
  else level = 'normal'
  return { level, seconds, sentinel: false, coveredUntilBar: future.covered_until_bar }
}

/** Fraction of the "normal" threshold this coverage represents, clamped 0..1. */
export function coverageFraction(coverage: Coverage): number {
  if (coverage.sentinel) return 1
  if (coverage.seconds === null) return 0
  return Math.max(0, Math.min(1, coverage.seconds / COVERAGE_THRESHOLDS.normal))
}

export function isUrgent(level: CoverageLevel): boolean {
  return level === 'warning' || level === 'critical'
}
