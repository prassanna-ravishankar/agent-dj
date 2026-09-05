/**
 * The top edge: recording hairline plus runtime and set-conductor health blocks.
 *
 * Recording is a persistent red hairline along the FULL top edge of the viewport —
 * impossible to miss, impossible to mistake for anything else. Conductor absence is rendered
 * calmly: it is a survivable, designed state, not an error.
 */

import type { ProcessHealth } from '../adapter/types'
import styles from './TopEdge.module.css'

interface Props {
  runtime: ProcessHealth
  conductor: ProcessHealth
  recording: boolean
  sessionId: string
  demo: boolean
}

function HealthBlock({
  name,
  health,
  absentNote,
}: {
  name: string
  health: ProcessHealth
  absentNote: string
}) {
  return (
    <div
      className={styles.block}
      data-state={health.running ? 'running' : 'absent'}
      title={health.running ? `pid ${health.pid}` : absentNote}
    >
      <span className={styles.mark} aria-hidden="true" />
      <span className={`label ${styles.blockLabel}`}>{name}</span>
      <span className={styles.blockValue}>{health.running ? 'running' : 'stopped'}</span>
    </div>
  )
}

export function TopEdge({ runtime, conductor, recording, sessionId, demo }: Props) {
  return (
    <>
      <div
        className={styles.edge}
        data-state={recording ? 'recording' : 'idle'}
        role={recording ? 'status' : undefined}
        aria-label={recording ? 'Recording master bus' : undefined}
      />
      <header className={styles.bar}>
        <div className={styles.left}>
          {recording ? (
            <span className={styles.recording}>
              <span className={styles.recordingMark} aria-hidden="true" />
              REC
            </span>
          ) : null}
          <HealthBlock
            name="Runtime"
            health={runtime}
            absentNote="SuperCollider is not running; this system is producing no audio."
          />
          <HealthBlock
            name="Conductor"
            health={conductor}
            absentNote="No new set cues will be made. Audio continues on the current deck."
          />
        </div>
        <div className={styles.right}>
          {demo ? (
            <span className={styles.demo} data-state="demo">
              DEMO DATA
            </span>
          ) : null}
          <span className={`mono ${styles.session}`}>{sessionId}</span>
        </div>
      </header>
      {!conductor.running && runtime.running ? (
        <p className={styles.agentNote} data-state="agent-absent">
          <span className={styles.agentNoteMark} aria-hidden="true" />
          No new set cues — the current deck continues. Start or resume the conductor from Set.
        </p>
      ) : null}
    </>
  )
}
