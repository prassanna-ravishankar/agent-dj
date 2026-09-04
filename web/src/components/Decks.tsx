/**
 * Two asymmetric deck bodies with the PHRASE SEAM (fused from probe B).
 *
 * The on-air deck is materially wider and is the only surface that emits. During a pending
 * transition the seam moves across the pair toward its landing bar, previewing the swap —
 * this is the signature crossfade interaction. Probe B's process-step footer is deliberately
 * NOT inherited: those steps describe a workflow the system does not have.
 *
 * energy is agent-maintained (dj/policy.py energy_delta), never measured from audio, and is
 * labelled as intent everywhere it appears.
 */

import type { DeckName, DeckState } from '../adapter/types'
import type { ChainEntity } from '../adapter/chain'
import { SegmentReadout } from './SegmentReadout'
import styles from './Decks.module.css'

interface Props {
  decks: Record<DeckName, DeckState>
  onAir: DeckName | null
  pending: ChainEntity | null
  /** 0..1 progress of the pending transition toward its landing bar; null when unknown. */
  seamProgress: number | null
  barsUntilLanding: number | null
  focused: DeckName
  onFocus: (deck: DeckName) => void
}

const STATUS_TEXT: Record<DeckState['status'], string> = {
  playing: 'ON AIR',
  prepared: 'PREPARED',
  preparing: 'PREPARING',
  stopped: 'STOPPED',
  failed: 'FAILED',
}

export function Decks({
  decks,
  onAir,
  pending,
  seamProgress,
  barsUntilLanding,
  focused,
  onFocus,
}: Props) {
  const target = pending?.decision?.target_deck ?? null

  return (
    <section className={styles.decks} aria-label="Decks">
      {(['A', 'B'] as const).map((name) => {
        const deck = decks[name]
        const live = onAir === name
        const displayedStatus = deck.status === 'playing' && !live ? 'prepared' : deck.status
        const incoming = target === name && barsUntilLanding !== null
        return (
          <article
            key={name}
            className={styles.deck}
            data-state={
              live
                ? 'on-air'
                : displayedStatus === 'preparing'
                  ? 'preparing'
                  : displayedStatus === 'failed'
                    ? 'generation-failed'
                    : 'prepared'
            }
            data-live={live ? 'true' : 'false'}
            data-focused={focused === name ? 'true' : 'false'}
            tabIndex={0}
            onFocus={() => onFocus(name)}
            aria-label={`Deck ${name}, ${STATUS_TEXT[displayedStatus].toLowerCase()}`}
          >
            {/* Non-colour signal for on air: a solid left edge marker. */}
            <span className={styles.marker} aria-hidden="true" />

            <header className={styles.head}>
              <div>
                <span className={`label ${styles.deckLabel}`}>Deck {name}</span>
                <p className={styles.status} data-status={displayedStatus}>
                  {STATUS_TEXT[displayedStatus]}
                </p>
              </div>
              <div className={styles.readouts}>
                <SegmentReadout
                  value={deck.gain_db}
                  cells={3}
                  label="Gain"
                  unit="dB"
                  size="sm"
                  tone={live ? 'amber' : 'slate'}
                  decimals={0}
                />
                <SegmentReadout
                  value={deck.energy === null ? null : Math.round(deck.energy * 100)}
                  cells={3}
                  label="Energy (intent)"
                  unit="%"
                  size="sm"
                  tone={live ? 'amber' : 'slate'}
                  unavailableText="no energy intent set"
                />
              </div>
            </header>

            {deck.prompt ? (
              <p className={styles.prompt}>{deck.prompt}</p>
            ) : (
              <p className={styles.empty}>
                Nothing prepared. Generate material for this deck before bringing it on air.
              </p>
            )}

            <footer className={styles.foot}>
              <span className={`mono ${styles.meta}`}>{deck.source}</span>
              {deck.duration_seconds !== null ? (
                <span className={`mono ${styles.meta}`}>{deck.duration_seconds}s loop</span>
              ) : (
                <span className={`mono ${styles.metaAbsent}`}>no audio</span>
              )}
              {deck.status === 'failed' ? (
                <span className={styles.failed}>
                  <span className={styles.failedMark} aria-hidden="true" />
                  generation failed — the other deck continues
                </span>
              ) : null}
              {incoming ? (
                <span className={styles.incoming}>
                  lands in {Math.max(0, Math.ceil(barsUntilLanding))}{' '}
                  {Math.ceil(barsUntilLanding) === 1 ? 'bar' : 'bars'}
                  {pending?.observation ? ` · ${pending.observation.kind.replace('-', ' ')}` : ''}
                </span>
              ) : null}
            </footer>

            {deck.status === 'preparing' ? (
              <div className={styles.preparing} aria-label="Preparing">
                <span className={styles.preparingFill} />
              </div>
            ) : null}
          </article>
        )
      })}

      {/* The phrase seam: a lit boundary travelling toward the landing bar. */}
      {seamProgress !== null && target !== null ? (
        <div
          className={styles.seam}
          style={{ ['--seam' as string]: `${seamProgress * 100}%` }}
          data-target={target}
          aria-hidden="true"
        />
      ) : null}

      <p className="visually-hidden" aria-live="polite">
        {onAir ? `Deck ${onAir} is on air.` : 'No deck is on air.'}
      </p>
    </section>
  )
}
