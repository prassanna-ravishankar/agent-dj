/**
 * THE CAUSAL CHAIN — one entity per observation accruing four stages (fused from probe C):
 * Observation → Decision → Generation → Schedule.
 *
 * This is content, not a debug log. `goal` and `evidence` are already written in human
 * language by dj/policy.py, so they are quoted directly. Probe C's fabricated metric grids
 * are deliberately not inherited — every value here comes from an artifact the system writes.
 */

import type { ChainEntity, Stage } from '../adapter/chain'
import { STAGE_ORDER } from '../adapter/chain'
import styles from './Chain.module.css'

interface Props {
  entities: ChainEntity[]
  id?: string
}

const STAGE_INDEX = new Map(STAGE_ORDER.map((name, i) => [name, i]))

function relativeTime(iso: string, now: number): string {
  const delta = Math.max(0, now - Date.parse(iso))
  const seconds = Math.round(delta / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.round(minutes / 60)}h ago`
}

function StageDot({ stage }: { stage: Stage }) {
  return (
    <span
      className={styles.dot}
      data-status={stage.status}
      data-stage={stage.name}
      aria-hidden="true"
    />
  )
}

export function Chain({ entities, id }: Props) {
  const now = Date.now()

  if (entities.length === 0) {
    return (
      <aside className={styles.chain} id={id} aria-label="Causal chain" tabIndex={-1}>
        <h2 className={`label ${styles.heading}`}>Chain</h2>
        <p className={styles.empty}>
          No observations yet. Feedback, and later microphone or camera input, will appear here as
          it becomes a decision and a scheduled change.
        </p>
      </aside>
    )
  }

  return (
    <aside className={styles.chain} id={id} aria-label="Causal chain" tabIndex={-1}>
      <h2 className={`label ${styles.heading}`}>Chain</h2>
      <ol className={styles.list}>
        {entities.map((entity) => {
          const reached = entity.stages.filter((s) => s.status === 'complete').length
          return (
            <li
              key={entity.observationId}
              className={styles.entity}
              data-state={
                entity.failed ? 'generation-failed' : entity.executed ? 'complete' : 'pending'
              }
            >
              <header className={styles.entityHead}>
                <span className={styles.kind}>
                  {entity.observation?.kind.replace('-', ' ') ?? 'observation'}
                </span>
                <span className={`mono ${styles.time}`}>{relativeTime(entity.ts, now)}</span>
              </header>

              {/* Four stages accruing, in order. */}
              <div className={styles.stages}>
                {entity.stages.map((stage) => (
                  <div
                    key={stage.name}
                    className={styles.stage}
                    data-status={stage.status}
                    data-reached={
                      (STAGE_INDEX.get(stage.name) ?? 0) < reached ? 'true' : 'false'
                    }
                  >
                    <StageDot stage={stage} />
                    <span className={styles.stageName}>{stage.name}</span>
                    {stage.detail ? (
                      <span className={styles.stageDetail}>{stage.detail}</span>
                    ) : (
                      <span className={styles.stagePending}>pending</span>
                    )}
                  </div>
                ))}
              </div>

              {entity.decision ? (
                <p className={styles.evidence}>
                  {entity.decision.evidence.join(' · ')}
                </p>
              ) : null}
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
