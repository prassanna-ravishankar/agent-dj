import { FormEvent, useMemo, useState } from 'react'
import type { DJClient } from '../adapter/client'
import type { Snapshot } from '../adapter/types'
import styles from './SetSteerer.module.css'

interface Props {
  snapshot: Snapshot
  client: DJClient
  demo: boolean
  onRefresh: () => Promise<void>
  announce: (message: string) => void
}

const PHASES = ['ARRIVAL', 'GATHER', 'RISE', 'CREST', 'RETURN', 'LANDING']
const DEFAULT_BRIEF =
  'Modern Indian house fusion — warm hand percussion, deep bass, modal melody, patient evolution, stable timbre'

function clock(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function remaining(endsAt: string | null): string {
  if (!endsAt) return '—'
  const minutes = Math.max(0, Math.ceil((Date.parse(endsAt) - Date.now()) / 60_000))
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')} left`
}

export function SetSteerer({ snapshot, client, demo, onRefresh, announce }: Props) {
  const performance = snapshot.conductor.set
  const active = snapshot.runtime.running && snapshot.conductor.running &&
    (performance.status === 'running' || performance.status === 'held')
  const [brief, setBrief] = useState(DEFAULT_BRIEF)
  const [minutes, setMinutes] = useState(90)
  const [steering, setSteering] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const timedProgress = performance.started_at && performance.ends_at
    ? (Date.now() - Date.parse(performance.started_at)) /
      Math.max(1, Date.parse(performance.ends_at) - Date.parse(performance.started_at))
    : performance.progress
  const progress = Math.max(0, Math.min(1, timedProgress))
  const phaseIndex = useMemo(
    () => Math.max(0, PHASES.findIndex((phase) => phase.toLowerCase() === performance.phase)),
    [performance.phase],
  )

  const act = async (label: string, action: () => Promise<{ ok: boolean; error?: unknown }>) => {
    if (demo) {
      announce(`${label} is unavailable in demo mode.`)
      setNotice(`${label} is unavailable in demo mode.`)
      return
    }
    setBusy(label)
    setNotice(null)
    announce(`${label} in progress.`)
    const result = await action()
    setBusy(null)
    if (!result.ok) {
      const error = result.error as { message?: string; detail?: string } | undefined
      const message = `${label} failed. ${error?.detail ?? error?.message ?? ''}`
      announce(message)
      setNotice(message)
      return
    }
    announce(`${label} accepted.`)
    await onRefresh()
  }

  const start = (event: FormEvent) => {
    event.preventDefault()
    void act('Start set', () => client.startSet(brief, minutes))
  }

  const steer = (event: FormEvent) => {
    event.preventDefault()
    const text = steering.trim()
    if (!text) return
    setSteering('')
    void act('Steering', () => client.steerSet(text))
  }

  if (snapshot.conductor.running && !snapshot.runtime.running) {
    return (
      <section className={styles.recovery} aria-labelledby="runtime-lost-title">
        <p className={styles.kicker}>AUDIO RUNTIME STOPPED</p>
        <h1 id="runtime-lost-title">No music is playing.</h1>
        <p>
          The conductor process is still waiting, but it cannot make audible moves without the
          audio runtime. Clear that stranded plan, then start a fresh set when you are ready.
        </p>
        <button
          className={styles.recoveryButton}
          type="button"
          disabled={Boolean(busy)}
          onClick={() => void act('Clear stranded conductor', () => client.endSet())}
        >
          {busy ? 'CLEARING…' : 'CLEAR CONDUCTOR · DO NOT START AUDIO'}
        </button>
        {notice ? <p className={styles.notice} role="alert">{notice}</p> : null}
      </section>
    )
  }

  if (!active) {
    const interrupted = performance.status === 'interrupted' ||
      (performance.status === 'running' && !snapshot.conductor.running)
    return (
      <section className={styles.stopped} aria-labelledby="set-title">
        <div className={styles.introBand}>
          <p className={styles.kicker}>LOCAL SET STEERER</p>
          <h1 id="set-title">What should the next hour feel like?</h1>
          <p className={styles.lede}>
            Give one broad direction. The local conductor shapes an arc, prepares each next passage,
            and keeps a safe loop underneath. You can interrupt it in plain language at any time.
          </p>
        </div>
        <form className={styles.briefDesk} onSubmit={start}>
          <label className={styles.fieldLabel} htmlFor="set-brief">THE BRIEF</label>
          <textarea
            id="set-brief"
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            rows={4}
            maxLength={1000}
            placeholder="Warm, groovy, slowly strange…"
          />
          <div className={styles.startRail}>
            <label className={styles.duration}>
              <span>LENGTH</span>
              <select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))}>
                <option value={60}>1 hour</option>
                <option value={90}>1 hour 30</option>
                <option value={120}>2 hours</option>
                <option value={180}>3 hours</option>
              </select>
            </label>
            <div className={styles.promise}>
              <span>EVENT-DRIVEN</span>
              <strong>No hosted tokens</strong>
            </div>
            <button className={styles.startButton} disabled={!brief.trim() || Boolean(busy)} type="submit">
              {busy ? 'SETTING THE ROOM…' : `START ${minutes}-MINUTE SET`}
            </button>
          </div>
          {interrupted ? <p className={styles.note}>The previous conductor stopped. Audio state is unchanged; starting again creates a fresh arc.</p> : null}
          {!snapshot.state.decks.A.audio_path ? <p className={styles.note}>First start will prepare a local safety loop before audio begins.</p> : null}
          <p className={styles.note}>Nothing starts until you press Start. Ending the conductor never cuts the audio.</p>
          {notice ? <p className={styles.notice} role="alert">{notice}</p> : null}
        </form>
      </section>
    )
  }

  return (
    <section className={styles.live} aria-labelledby="live-set-title">
      <header className={styles.onAirBand}>
        <div>
          <p className={styles.kicker}>{performance.status === 'held' ? 'HELD · AUDIO CONTINUES' : 'ON AIR · LOCAL CONDUCTOR'}</p>
          <h1 id="live-set-title">{performance.brief}</h1>
        </div>
        <div className={styles.timeBlock}>
          <span>{clock(performance.started_at)}—{clock(performance.ends_at)}</span>
          <strong>{remaining(performance.ends_at)}</strong>
        </div>
      </header>

      <div className={styles.arc} aria-label={`Set ${Math.round(progress * 100)} percent complete`}>
        <div className={styles.arcHeader}>
          <span>THE ARC</span><strong>{Math.round(progress * 100)}%</strong>
        </div>
        <div className={styles.track}>
          <span className={styles.fill} style={{ width: `${progress * 100}%` }} />
          <span className={styles.playhead} style={{ left: `${progress * 100}%` }} />
        </div>
        <div className={styles.phaseLabels}>
          {PHASES.map((phase, index) => (
            <span key={phase} data-active={index === phaseIndex ? 'true' : 'false'}>{phase}</span>
          ))}
        </div>
      </div>

      <div className={styles.programme}>
        <article className={styles.now}>
          <div className={styles.programmeHead}><span>NOW</span><strong>{performance.phase}</strong></div>
          <p>{performance.current_note ?? 'Holding the current passage.'}</p>
        </article>
        <article className={styles.next}>
          <div className={styles.programmeHead}><span>NEXT CUE</span><strong>{performance.activity.toUpperCase()} · {clock(performance.next_cue_at)}</strong></div>
          <p>{performance.next_note ?? 'No new cue while the conductor is held.'}</p>
        </article>
      </div>

      <form className={styles.steerDesk} onSubmit={steer}>
        <label htmlFor="steering">TELL THE DJ</label>
        <div className={styles.composer}>
          <input
            id="steering"
            value={steering}
            onChange={(event) => setSteering(event.target.value)}
            placeholder="More tabla, less synth; lift it after the next phrase…"
            maxLength={1000}
          />
          <button type="submit" disabled={!steering.trim() || Boolean(busy)}>STEER NEXT PASSAGE</button>
        </div>
        <div className={styles.interventions}>
          {['More energy, keep it musical', 'Less busy, keep the pulse', 'Bring the Indian percussion forward'].map((text) => (
            <button key={text} type="button" disabled={Boolean(busy)} onClick={() => void act(text, () => client.steerSet(text))}>{text}</button>
          ))}
          <button
            type="button"
            data-hold="true"
            disabled={Boolean(busy)}
            onClick={() => void act(performance.status === 'held' ? 'Resume conductor' : 'Hold conductor', () =>
              performance.status === 'held' ? client.resumeSet() : client.holdSet())}
          >
            {performance.status === 'held' ? 'Resume decisions' : 'Hold this'}
          </button>
        </div>
        {notice ? <p className={styles.notice} role="alert">{notice}</p> : null}
      </form>

      <footer className={styles.liveFoot}>
        <span>Current music survives browser or conductor failure.</span>
        <button type="button" disabled={Boolean(busy)} onClick={() => void act('End conductor', () => client.endSet())}>END CONDUCTOR · KEEP MUSIC PLAYING</button>
      </footer>
    </section>
  )
}
