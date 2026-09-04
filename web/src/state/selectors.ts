/**
 * Pure selectors over a Snapshot. Everything derived, nothing stored.
 */

import type { DeckName, Snapshot } from '../adapter/types'
import { deriveClock, type MusicalClock } from '../adapter/clock'
import { deriveCoverage, type Coverage } from '../adapter/coverage'
import { buildChain, inFlight, type ChainEntity } from '../adapter/chain'
import { isRecording } from '../demo/fixtures'

export interface View {
  clock: MusicalClock
  coverage: Coverage
  chain: ChainEntity[]
  pending: ChainEntity | null
  onAir: DeckName | null
  recording: boolean
  /** 0..1 progress of the pending transition; null when the clock cannot support it. */
  seamProgress: number | null
  barsUntilLanding: number | null
}

export function selectView(snapshot: Snapshot, now: number = Date.now()): View {
  const clock = deriveClock(snapshot.state, now)
  const coverage = deriveCoverage(snapshot.state.future)
  const chain = buildChain(
    snapshot.state.observations,
    snapshot.decisions,
    snapshot.schedules,
    snapshot.events,
  )
  const flying = inFlight(chain)
  const pending = flying.length > 0 ? (flying[0] ?? null) : null

  // A persisted deck can still say `playing` after the runtime has stopped. Playback truth
  // requires all three signals; never turn stale session state into an "on air" claim.
  const onAir = snapshot.runtime.running && snapshot.state.transport.playing
    ? ((Object.values(snapshot.state.decks).find((d) => d.status === 'playing')?.name as
        | DeckName
        | undefined) ?? null)
    : null

  let barsUntilLanding: number | null = null
  let seamProgress: number | null = null

  if (pending?.atBar !== null && pending !== null && clock.bar !== null) {
    barsUntilLanding = pending.atBar - clock.bar
    // The seam sweeps across the pair as the landing bar approaches. The window is the
    // decision's own transition length, so the preview matches the real crossfade.
    const window = pending.decision?.transition_bars ?? 4
    const travelled = 1 - Math.max(0, Math.min(1, barsUntilLanding / (window * 4)))
    seamProgress = travelled
  }

  return {
    clock,
    coverage,
    chain,
    pending,
    onAir,
    recording: isRecording(snapshot.events),
    seamProgress,
    barsUntilLanding,
  }
}
