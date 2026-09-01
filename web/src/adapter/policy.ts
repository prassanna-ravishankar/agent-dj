/**
 * MIRROR of dj/policy.py LocalDJPolicy — for PREVIEW ONLY.
 *
 * NOT AUTHORITATIVE. The Python policy decides; this table exists so a control can print its
 * own consequence before the decision comes back, and so the ghost tick can be placed at the
 * right bar. If Python and this table ever disagree, Python is right — the surface must
 * replace the preview with the real decision as soon as it arrives.
 *
 * tests/contract.test.ts pins these values against the policy table in dj/policy.py.
 */

import type { FeedbackKind } from './types'

export interface FeedbackConsequence {
  kind: FeedbackKind
  /** Display label; the CLI value is `kind`. */
  label: string
  /** dj/policy.py goal string, verbatim. */
  goal: string
  /** transition_bars from the policy table. */
  bars: number
  /** energy_delta from the policy table. */
  energyDelta: number
  /** Keyboard digit, 1-6. */
  key: string
}

export const FEEDBACK: readonly FeedbackConsequence[] = [
  {
    kind: 'love',
    label: 'LOVE',
    goal: 'reinforce what is working without a sharp change',
    bars: 8,
    energyDelta: 0.05,
    key: '1',
  },
  {
    kind: 'dislike',
    label: 'DISLIKE',
    goal: 'move to a coherent alternative direction',
    bars: 4,
    energyDelta: -0.05,
    key: '2',
  },
  {
    kind: 'more-energy',
    label: 'MORE ENERGY',
    goal: 'increase energy through density and drive',
    bars: 4,
    energyDelta: 0.2,
    key: '3',
  },
  {
    kind: 'less-energy',
    label: 'LESS ENERGY',
    goal: 'release energy while preserving continuity',
    bars: 8,
    energyDelta: -0.2,
    key: '4',
  },
  {
    kind: 'boring',
    label: 'BORING',
    goal: 'introduce novelty without abandoning the set',
    bars: 4,
    energyDelta: 0.1,
    key: '5',
  },
  {
    kind: 'weird',
    label: 'WEIRD',
    goal: 'take a controlled unexpected detour',
    bars: 4,
    energyDelta: 0.05,
    key: '6',
  },
] as const

export function consequenceFor(kind: FeedbackKind): FeedbackConsequence {
  const found = FEEDBACK.find((f) => f.kind === kind)
  if (!found) throw new Error(`unknown feedback kind: ${kind}`)
  return found
}

/** Signed energy delta as printed on the control, e.g. "+0.20". */
export function formatDelta(delta: number): string {
  return `${delta >= 0 ? '+' : '−'}${Math.abs(delta).toFixed(2)}`
}

/** Crossfade lengths the surface offers. Bars are the vocabulary, not seconds. */
export const CROSSFADE_BARS = [4, 8, 16, 32] as const
