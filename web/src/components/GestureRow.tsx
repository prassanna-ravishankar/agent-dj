/**
 * The six feedback gestures — the primary controls.
 *
 * Each control PERMANENTLY PRINTS ITS OWN CONSEQUENCE (fused from the cassette-futurist
 * challenger): kind, transition length in bars, and energy delta. The performer never has to
 * recall the policy table; it is on the surface. Values mirror dj/policy.py and are labelled
 * as a preview — Python decides.
 */

import type { FeedbackKind } from '../adapter/types'
import { FEEDBACK, formatDelta } from '../adapter/policy'
import styles from './GestureRow.module.css'

interface Props {
  onFeedback: (kind: FeedbackKind) => void
  /** Kind currently awaiting confirmation from the control plane. */
  pendingKind: FeedbackKind | null
  disabled: boolean
  disabledReason: string | null
}

export function GestureRow({ onFeedback, pendingKind, disabled, disabledReason }: Props) {
  return (
    <section className={styles.row} aria-label="Feedback gestures">
      {FEEDBACK.map((f) => {
        const pending = pendingKind === f.kind
        return (
          <button
            key={f.kind}
            type="button"
            className={styles.gesture}
            data-state={pending ? 'pending' : 'idle'}
            disabled={disabled}
            onClick={() => onFeedback(f.kind)}
            title={disabled && disabledReason ? disabledReason : f.goal}
            aria-keyshortcuts={f.key}
          >
            <span className={styles.key} aria-hidden="true">
              {f.key}
            </span>
            <span className={styles.label}>{f.label}</span>
            {/* The consequence, printed permanently. */}
            <span className={`mono ${styles.consequence}`}>
              {f.bars} bars · {formatDelta(f.energyDelta)}
            </span>
            <span className={styles.goal}>{f.goal}</span>
            {pending ? (
              <span className={styles.pending}>
                <span className={styles.pendingMark} aria-hidden="true" />
                sent
              </span>
            ) : null}
          </button>
        )
      })}
      {disabled && disabledReason ? (
        <p className={styles.note}>{disabledReason}</p>
      ) : null}
    </section>
  )
}
