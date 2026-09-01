/**
 * Fixed-cell seven-segment readout with designed UNLIT GHOST SEGMENTS.
 *
 * This is the load-bearing honesty mechanism of the whole surface. A ghost cell shows
 * "this cell exists and its value is absent" without inventing a zero, structurally
 * distinguishing absent / empty / zero in a way colour alone cannot (PRODUCT.md 13.4).
 *
 * Used for: the bar counter (ghosted when the clock is uncertain), master loudness (always
 * ghosted today — peak_dbfs and lufs_short are null in every recorded session), and any deck
 * field that is null.
 *
 * Cells are fixed width, so digits never reflow and the eye returns to the same position.
 */

import styles from './SegmentReadout.module.css'

interface Props {
  /** null renders ghost cells — never substitute a fallback number. */
  value: number | string | null
  /** Total cells; the value is right-aligned within them. */
  cells: number
  label?: string
  unit?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  tone?: 'amber' | 'slate' | 'ember' | 'red' | 'ink'
  /** Accessible text used when value is null. */
  unavailableText?: string
  decimals?: number
}

function format(value: number | string, decimals: number | undefined): string {
  if (typeof value === 'string') return value
  return decimals === undefined ? String(Math.trunc(value)) : value.toFixed(decimals)
}

export function SegmentReadout({
  value,
  cells,
  label,
  unit,
  size = 'md',
  tone = 'amber',
  unavailableText = 'unavailable',
  decimals,
}: Props) {
  const absent = value === null
  const text = absent ? '' : format(value, decimals)
  const padded = text.padStart(cells, ' ')
  const glyphs = padded.slice(-cells).split('')

  // A ghost segment means "this value is absent", so it may only be painted when the WHOLE
  // readout is absent. Painting ghosts in the unused leading cells of a present value makes
  // 184 read as "8184" and 0 read as "880" — the opposite of the honesty this is here for.
  const ghosted = absent

  return (
    <div
      className={`${styles.readout} ${styles[size]} ${styles[tone]}`}
      data-value={absent ? 'unavailable' : 'present'}
    >
      {label ? <span className={`label ${styles.label}`}>{label}</span> : null}
      <div
        className={styles.cells}
        role="img"
        aria-label={ariaLabel(label, text, unit, absent, unavailableText)}
        data-ghosted={ghosted ? 'true' : 'false'}
      >
        {glyphs.map((glyph, index) => (
          <span
            key={index}
            aria-hidden="true"
            className={styles.cell}
            data-lit={glyph !== ' ' ? 'true' : 'false'}
          >
            {/*
              The unlit ghost is painted by CSS (content: '8'), never as text content, so it
              cannot leak into textContent or be read as a digit by assistive technology.
            */}
            <span className={styles.glyph}>{glyph === ' ' ? '' : glyph}</span>
          </span>
        ))}
        {unit ? <span className={styles.unit}>{unit}</span> : null}
      </div>
    </div>
  )
}

function ariaLabel(
  label: string | undefined,
  text: string,
  unit: string | undefined,
  absent: boolean,
  unavailableText: string,
): string {
  const name = label ? `${label}: ` : ''
  if (absent) return `${name}${unavailableText}`
  return `${name}${text}${unit ? ` ${unit}` : ''}`
}
