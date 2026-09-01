/**
 * THE HORIZON — the protagonist (probe A topology).
 *
 * Left edge is NOW (on-air, guaranteed). Rightward is the future you have bought yourself.
 * Bars are the horizontal unit, so phrase-aligned latency reads as DISTANCE, not delay.
 *
 * Scheduled intents appear as ticks at their target bar and travel left toward now
 * (fused from probe C). When the clock is uncertain, the whole horizon withdraws its
 * spatial claim rather than drawing plausible wrong positions.
 */

import { useMemo } from 'react'
import type { Coverage } from '../adapter/coverage'
import { coverageFraction } from '../adapter/coverage'
import type { MusicalClock } from '../adapter/clock'
import { CLOCK_REASON_TEXT, displayBar } from '../adapter/clock'
import type { ChainEntity } from '../adapter/chain'
import { SegmentReadout } from './SegmentReadout'
import styles from './Horizon.module.css'

interface Props {
  clock: MusicalClock
  coverage: Coverage
  inFlight: ChainEntity[]
  runtimeRunning: boolean
}

/** Bars of future the horizon spans left-to-right. One 32-bar phrase plus headroom. */
const HORIZON_BARS = 48

export function Horizon({ clock, coverage, inFlight, runtimeRunning }: Props) {
  const bar = displayBar(clock)

  // Coverage falloff position. The sentinel fills the band; a finite value is scaled
  // against the "normal" threshold so warning/critical visibly pull toward now.
  const falloff = useMemo(() => {
    if (!runtimeRunning) return 0
    if (coverage.sentinel) return 1
    return coverageFraction(coverage)
  }, [coverage, runtimeRunning])

  if (!runtimeRunning) {
    return (
      <section className={styles.horizon} data-state="offline" aria-label="Coverage horizon">
        <div className={styles.offline}>
          <span className={styles.offlineMark} aria-hidden="true" />
          <div>
            <p className={styles.offlineTitle}>Runtime offline</p>
            <p className={styles.offlineBody}>
              This system is not producing audio. Nothing is scheduled and no coverage is held.
            </p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section
      className={styles.horizon}
      data-state={clock.uncertain ? 'clock-uncertain' : `coverage-${coverage.level}`}
      aria-label="Coverage horizon"
    >
      <div className={styles.nowColumn}>
        <span className={`label ${styles.nowLabel}`}>Now</span>
        <SegmentReadout
          value={bar}
          cells={4}
          label="Bar"
          size="xl"
          tone={clock.uncertain ? 'ink' : 'amber'}
          unavailableText="bar position unavailable"
        />
        {clock.uncertain ? (
          <p className={styles.uncertain} data-state="clock-uncertain">
            <span className={styles.uncertainMark} aria-hidden="true" />
            Clock uncertain — {CLOCK_REASON_TEXT[clock.reasons[0] ?? 'contradiction']} Music is
            unaffected.
          </p>
        ) : null}
      </div>

      <div className={styles.field}>
        {/* Coverage band: the lit region is guaranteed audio, falling off into the ground. */}
        <div
          className={styles.band}
          style={{
            ['--falloff' as string]: `${falloff * 100}%`,
            ['--falloff-frac' as string]: falloff,
          }}
          data-level={coverage.level}
          data-uncertain={clock.uncertain ? 'true' : 'false'}
        >
          <div className={styles.lit} />
          <div className={styles.edge} />
        </div>

        {/* Bar ruler. Withdrawn entirely when the clock cannot support positions. */}
        {!clock.uncertain && bar !== null ? (
          <div className={styles.ruler} aria-hidden="true">
            {Array.from({ length: HORIZON_BARS + 1 }, (_, i) => {
              const barNumber = bar + i
              const phrase = barNumber % 16 === 0
              const half = barNumber % 4 === 0
              return (
                <span
                  key={i}
                  className={styles.tick}
                  data-weight={phrase ? 'phrase' : half ? 'half' : 'beat'}
                  style={{ left: `${(i / HORIZON_BARS) * 100}%` }}
                />
              )
            })}
          </div>
        ) : null}

        {/* Intents travelling toward their landing bar. */}
        <div className={styles.intents}>
          {clock.uncertain || bar === null
            ? null
            : inFlight.map((entity) => {
                if (entity.atBar === null) return null
                const distance = entity.atBar - (clock.bar ?? 0)
                if (distance < -1 || distance > HORIZON_BARS) return null
                const left = Math.max(0, (distance / HORIZON_BARS) * 100)
                const bars = Math.max(0, Math.ceil(distance))
                const label = entity.observation?.kind.replace('-', ' ') ?? 'change'
                return (
                  <div
                    key={entity.observationId}
                    className={styles.intent}
                    style={{ left: `${left}%` }}
                    data-state="pending"
                  >
                    <span className={styles.intentStem} aria-hidden="true" />
                    <span className={styles.intentBody}>
                      <span className={styles.intentKind}>{label}</span>
                      <span className={`mono ${styles.intentLands}`}>
                        lands in {bars} {bars === 1 ? 'bar' : 'bars'}
                      </span>
                      {entity.decision ? (
                        <span className={styles.intentGoal}>{entity.decision.goal}</span>
                      ) : null}
                    </span>
                  </div>
                )
              })}
        </div>

        <div className={styles.coverageReadout}>
          {coverage.sentinel ? (
            <div className={styles.safe} data-state="coverage-safe">
              <span className={styles.safeMark} aria-hidden="true" />
              <span className={styles.safeWord}>SAFE</span>
              <span className={styles.safeNote}>a looping deck holds audio indefinitely</span>
            </div>
          ) : (
            <div className={styles.covered} data-level={coverage.level}>
              <SegmentReadout
                value={coverage.seconds}
                cells={3}
                label="Covered"
                unit="sec"
                size="sm"
                tone={
                  coverage.level === 'critical'
                    ? 'red'
                    : coverage.level === 'warning'
                      ? 'ember'
                      : 'amber'
                }
              />
              <span className={styles.coveredLevel} data-level={coverage.level}>
                {coverage.level === 'critical'
                  ? 'CRITICAL — extend coverage now'
                  : coverage.level === 'warning'
                    ? 'WARNING — extend coverage soon'
                    : 'covered'}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
