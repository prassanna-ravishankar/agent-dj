/**
 * Keyboard reference. A performer with one hand on a controller should not need a pointer.
 */

import { useEffect, useRef } from 'react'
import { FEEDBACK } from '../adapter/policy'
import styles from './ShortcutOverlay.module.css'

const OTHER: ReadonlyArray<{ keys: string; action: string }> = [
  { keys: 'A / B', action: 'Focus deck' },
  { keys: 'Space', action: 'Play the focused deck' },
  { keys: 'R', action: 'Toggle master recording (confirms first)' },
  { keys: '/', action: 'Jump to the causal chain' },
  { keys: '?', action: 'Show or hide this reference' },
  { keys: 'Esc', action: 'Close this reference' },
]

export function ShortcutOverlay({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    ref.current?.focus()
  }, [])

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        ref={ref}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className={styles.heading}>Keyboard</h2>
        <div className={styles.columns}>
          <dl className={styles.list}>
            {FEEDBACK.map((f) => (
              <div key={f.kind} className={styles.item}>
                <dt className={`mono ${styles.keys}`}>{f.key}</dt>
                <dd className={styles.action}>
                  {f.label}
                  <span className={styles.detail}>
                    {f.bars} bars · {f.goal}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
          <dl className={styles.list}>
            {OTHER.map((o) => (
              <div key={o.keys} className={styles.item}>
                <dt className={`mono ${styles.keys}`}>{o.keys}</dt>
                <dd className={styles.action}>{o.action}</dd>
              </div>
            ))}
          </dl>
        </div>
        <button type="button" className={styles.close} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}
