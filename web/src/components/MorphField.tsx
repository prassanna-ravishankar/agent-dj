import type { CSSProperties } from 'react'
import type { StreamPrompt } from '../adapter/types'
import styles from './MorphField.module.css'

interface Props {
  prompts: StreamPrompt[]
  draftWeights: number[]
  disabled: boolean
  busy: boolean
  onFocus: (slot: number) => void
}

const positions: Array<readonly [number, number]> = [
  [16, 24],
  [50, 13],
  [84, 24],
  [84, 74],
  [50, 87],
  [16, 74],
]

type FieldStyle = CSSProperties & Record<'--field-x' | '--field-y' | '--field-weight', string>

function nodeStyle(index: number, weight: number): FieldStyle {
  const [x, y] = positions[index] ?? ([50, 50] as const)
  return {
    '--field-x': `${x}%`,
    '--field-y': `${y}%`,
    '--field-weight': String(Math.max(0.08, weight)),
  }
}

export function MorphField({ prompts, draftWeights, disabled, busy, onFocus }: Props) {
  const populated = prompts.filter((prompt) => prompt.text.trim())
  const total = prompts.reduce((sum, prompt, index) => (
    prompt.text.trim() ? sum + Math.max(0, draftWeights[index] ?? prompt.weight) : sum
  ), 0)
  const centroid = prompts.reduce(
    (point, prompt, index) => {
      if (!prompt.text.trim()) return point
      const weight = Math.max(0, draftWeights[index] ?? prompt.weight)
      const [x, y] = positions[index] ?? ([50, 50] as const)
      return [point[0] + x * weight, point[1] + y * weight] as [number, number]
    },
    [0, 0] as [number, number],
  )
  const focusX = total > 0 ? centroid[0] / total : 50
  const focusY = total > 0 ? centroid[1] / total : 50

  return (
    <div className={styles.field} aria-label="Prompt gravity field">
      <div className={styles.legend}>
        <span>Prompt gravity</span>
        <small>Tap a direction to lean the music there</small>
      </div>
      <div
        className={styles.focus}
        aria-hidden="true"
        style={{ '--field-x': `${focusX}%`, '--field-y': `${focusY}%` } as CSSProperties}
      />
      {prompts.map((prompt, index) => {
        const weight = draftWeights[index] ?? prompt.weight
        const label = prompt.text.trim() || `Empty direction ${prompt.slot + 1}`
        return (
          <button
            type="button"
            className={styles.node}
            style={nodeStyle(index, weight)}
            key={prompt.slot}
            data-empty={!prompt.text.trim()}
            data-active={weight > 0}
            disabled={disabled || busy || !prompt.text.trim()}
            aria-label={`Lean into prompt ${prompt.slot + 1}: ${label}`}
            onClick={() => onFocus(prompt.slot)}
          >
            <span className={styles.nodeKey}>{String.fromCharCode(65 + prompt.slot)}</span>
            <span className={styles.nodeText}>{label}</span>
            <span className={styles.nodeWeight}>{Math.round(weight * 100)}%</span>
          </button>
        )
      })}
      <div className={styles.centre} aria-hidden="true">
        <span>{populated.length}</span>
        <small>directions</small>
      </div>
    </div>
  )
}
