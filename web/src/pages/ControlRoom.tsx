/**
 * Control room — continuous generation and the optional local Codex collaborator.
 *
 * Neither surface is on the audio path. The fallback state is kept in the first reading line:
 * a performer should never have to infer which source is actually audible.
 */

import { useEffect, useMemo, useState, type FormEvent } from 'react'
import type { DJClient } from '../adapter/client'
import type {
  CodexModelSummary,
  CodexThreadResponse,
  CodexThreadSummary,
  Result,
  Snapshot,
} from '../adapter/types'
import { MorphField } from '../components/MorphField'
import styles from './ControlRoom.module.css'

type PhraseBars = 4 | 8 | 16 | 32
type RoomView = 'play' | 'shape' | 'codex'

interface Props {
  snapshot: Snapshot
  client: DJClient
  demo: boolean
  onRefresh: () => Promise<void>
  announce: (message: string) => void
}

function threadList(value: { data?: CodexThreadSummary[]; threads?: CodexThreadSummary[] }) {
  return value.data ?? value.threads ?? []
}

function modelList(value: { data?: CodexModelSummary[]; models?: CodexModelSummary[] }) {
  return value.data ?? value.models ?? []
}

function threadTitle(thread: CodexThreadSummary): string {
  return thread.name || thread.preview || `Thread ${thread.id.slice(0, 8)}`
}

function displayTime(value: number | string | undefined): string | null {
  if (value === undefined) return null
  const parsed = typeof value === 'number'
    ? new Date(value < 1_000_000_000_000 ? value * 1000 : value)
    : new Date(value)
  if (Number.isNaN(parsed.valueOf())) return null
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

function itemText(record: Record<string, unknown>): string | null {
  for (const part of [record.text, record.message]) {
    if (typeof part === 'string' && part.trim()) return part
  }
  if (typeof record.content === 'string' && record.content.trim()) return record.content
  if (Array.isArray(record.content)) {
    const text = record.content
      .map((part) => {
        if (typeof part === 'string') return part
        if (!part || typeof part !== 'object') return ''
        const value = (part as Record<string, unknown>).text
        return typeof value === 'string' ? value : ''
      })
      .filter(Boolean)
      .join('\n')
    return text || null
  }
  return null
}

function extractTranscript(value: CodexThreadResponse | null): Array<{ id: string; role: string; text: string }> {
  const turns = value?.thread?.turns
  if (!Array.isArray(turns)) return []
  const lines: Array<{ id: string; role: string; text: string }> = []
  turns.slice(-8).forEach((turn, turnIndex) => {
    if (!turn || typeof turn !== 'object') return
    const items = (turn as Record<string, unknown>).items
    if (!Array.isArray(items)) return
    items.forEach((item, itemIndex) => {
      if (!item || typeof item !== 'object') return
      const record = item as Record<string, unknown>
      const text = itemText(record)
      if (!text) return
      const type = typeof record.type === 'string' ? record.type : 'message'
      const role = type.toLowerCase().includes('user') ? 'You' : 'Codex'
      lines.push({ id: `${turnIndex}-${itemIndex}`, role, text })
    })
  })
  return lines
}

export function ControlRoom({ snapshot, client, demo, onRefresh, announce }: Props) {
  const { stream, codex } = snapshot.state
  const [prompts, setPrompts] = useState(() => stream.prompts.map((prompt) => prompt.text))
  const [weights, setWeights] = useState(() => stream.prompts.map((prompt) => prompt.weight))
  const [morphSeconds, setMorphSeconds] = useState(8)
  const [scheduleSlot, setScheduleSlot] = useState(0)
  const [scheduleWeight, setScheduleWeight] = useState(1)
  const [phraseBars, setPhraseBars] = useState<PhraseBars>(4)
  const [morphBars, setMorphBars] = useState(8)
  const [temperature, setTemperature] = useState(stream.temperature)
  const [topK, setTopK] = useState(stream.top_k)
  const [dirtyPrompts, setDirtyPrompts] = useState<Set<number>>(() => new Set())
  const [dirtyWeights, setDirtyWeights] = useState<Set<number>>(() => new Set())
  const [dirtyTemperature, setDirtyTemperature] = useState(false)
  const [dirtyTopK, setDirtyTopK] = useState(false)
  const [threads, setThreads] = useState<CodexThreadSummary[]>([])
  const [models, setModels] = useState<CodexModelSummary[]>([])
  const [threadDetail, setThreadDetail] = useState<CodexThreadResponse | null>(null)
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('')
  const [creatingThread, setCreatingThread] = useState(false)
  const [roomView, setRoomView] = useState<RoomView>('play')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setPrompts((current) =>
      stream.prompts.map((item, index) =>
        dirtyPrompts.has(index) ? current[index] ?? item.text : item.text,
      ),
    )
    setWeights((current) =>
      stream.prompts.map((item, index) =>
        dirtyWeights.has(index) ? current[index] ?? item.weight : item.weight,
      ),
    )
    if (!dirtyTemperature) setTemperature(stream.temperature)
    if (!dirtyTopK) setTopK(stream.top_k)
  }, [dirtyPrompts, dirtyTemperature, dirtyTopK, dirtyWeights, stream])

  const run = async <T,>(
    label: string,
    operation: () => Promise<Result<T>>,
    afterRefresh?: () => void,
  ): Promise<T | null> => {
    if (demo) {
      announce(`${label} is unavailable in demo mode.`)
      return null
    }
    setBusy(label)
    setError(null)
    announce(`${label} in progress.`)
    const result = await operation()
    setBusy(null)
    if (!result.ok) {
      const message = `${result.error.message}${result.error.detail ? ` ${result.error.detail}` : ''}`
      setError(message)
      announce(`${label} failed.`)
      await onRefresh()
      return null
    }
    announce(`${label} accepted.`)
    await onRefresh()
    afterRefresh?.()
    return result.value
  }

  const refreshThreads = async () => {
    const value = await run('Refresh Codex threads', () => client.codexThreads())
    if (value) setThreads(threadList(value))
  }

  const readThread = async () => {
    const value = await run('Read Codex thread', () => client.readCodexThread())
    if (value) setThreadDetail(value)
  }

  useEffect(() => {
    if (demo || !snapshot.codex_bridge.running) return
    void client.codexThreads().then((result) => {
      if (result.ok) setThreads(threadList(result.value))
    })
    void client.codexModels().then((result) => {
      if (result.ok) setModels(modelList(result.value))
    })
  }, [client, demo, snapshot.codex_bridge.running])

  useEffect(() => {
    if (demo || !codex.thread_id || !snapshot.codex_bridge.running) return
    void client.readCodexThread().then((result) => {
      if (result.ok) setThreadDetail(result.value)
    })
  }, [client, codex.thread_id, codex.turn_status, demo, snapshot.codex_bridge.running])

  const transcript = useMemo(() => extractTranscript(threadDetail), [threadDetail])
  const runtimeRunning = snapshot.runtime.running
  const startupDeck = snapshot.state.decks.A
  const hasPreparedFallback = ['prepared', 'playing'].includes(startupDeck.status)
    && Boolean(startupDeck.audio_path)
  const activeTurn = Boolean(
    codex.turn_id &&
      !['completed', 'interrupted', 'failed', 'cancelled', 'idle', 'detached'].includes(
        codex.turn_status,
      ),
  )
  const audibleLabel = !runtimeRunning
    ? 'Nothing — runtime stopped'
    : stream.fallback_active
    ? stream.force_fallback
      ? 'Fallback locked'
      : 'Fallback protecting output'
    : stream.healthy
      ? 'MRT2 on air'
      : 'Source indeterminate'
  const audibleState = !runtimeRunning
    ? 'stopped'
    : stream.fallback_active
    ? 'fallback'
    : stream.healthy
      ? 'live'
      : 'indeterminate'

  const startThread = async (event: FormEvent) => {
    event.preventDefault()
    const value = await run('Start Codex thread', () =>
      client.newCodexThread(prompt.trim() || undefined, model.trim() || undefined),
    )
    if (value) {
      setPrompt('')
      setCreatingThread(false)
      setThreadDetail(value)
      void refreshThreads()
    }
  }

  const sendDirection = async (event: FormEvent) => {
    event.preventDefault()
    if (!prompt.trim()) return
    const value = await run('Send direction to Codex', () => client.sendCodexTurn(prompt.trim()))
    if (value) {
      setPrompt('')
      if (value.thread) setThreadDetail(value)
    }
  }

  const steerDirection = async () => {
    if (!prompt.trim()) return
    const value = await run('Steer active Codex turn', () => client.steerCodexTurn(prompt.trim()))
    if (value) setPrompt('')
  }

  const startPerformance = async () => run('Start performance', async (): Promise<Result<void>> => {
    // Start the guaranteed deck first. MRT2 is requested only after audio is alive, and its
    // independent guard keeps the fallback audible until signal qualification succeeds.
    const started = await client.startRuntime(false)
    if (!started.ok) return started
    if (!stream.available) return { ok: true, value: undefined }
    return client.streamControl(true, false)
  })

  const focusLane = async (slot: number) => {
    const lane = stream.prompts.find((item) => item.slot === slot)
    if (!lane?.text.trim()) return
    await run(`Lean into ${lane.text}`, async (): Promise<Result<void>> => {
      for (const promptLane of stream.prompts) {
        if (!promptLane.text.trim()) continue
        const result = await client.streamWeight(
          promptLane.slot,
          promptLane.slot === slot ? 1 : 0,
          morphSeconds,
        )
        if (!result.ok) return result
      }
      return { ok: true, value: undefined }
    }, () => setDirtyWeights(new Set()))
  }

  return (
    <div className={styles.room}>
      <header className={styles.statusLine}>
        <div>
          <h1>{audibleLabel}</h1>
          <p>{runtimeRunning ? 'The safety deck remains underneath every move.' : 'Start the local performance when you are ready to hear sound.'}</p>
        </div>
        <dl className={styles.audibleTruth} aria-label="Audible source status">
          <div>
            <dt>Audible now</dt>
            <dd data-state={audibleState}>{audibleLabel}</dd>
          </div>
          <div>
            <dt>Stream mix</dt>
            <dd className="mono">{Math.round(stream.mix * 100)}%</dd>
          </div>
          <div>
            <dt>Signal</dt>
            <dd className="mono">
              {stream.signal_level === null ? 'unavailable' : stream.signal_level.toFixed(3)}
            </dd>
          </div>
        </dl>
      </header>

      {error ? (
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      ) : null}

      <nav className={styles.roomSwitch} aria-label="Control room sections">
        <button
          type="button"
          data-active={roomView === 'play'}
          aria-pressed={roomView === 'play'}
          onClick={() => setRoomView('play')}
        >
          Play
        </button>
        <button
          type="button"
          data-active={roomView === 'shape'}
          aria-pressed={roomView === 'shape'}
          onClick={() => setRoomView('shape')}
        >
          Shape
        </button>
        <button
          type="button"
          data-active={roomView === 'codex'}
          aria-pressed={roomView === 'codex'}
          onClick={() => setRoomView('codex')}
        >
          Codex
        </button>
      </nav>

      <div className={styles.workbench}>
        {roomView === 'play' ? (
          <main className={styles.performance} aria-labelledby="performance-heading">
            <div className={styles.performanceHead}>
              <div>
                <h2 id="performance-heading">Move through the continuous sound</h2>
                <p>Each touch eases MRT2 toward one prompt. Nothing is cut or regenerated.</p>
              </div>
              <div className={styles.engineActions}>
                {runtimeRunning ? (
                  <>
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      disabled={demo || busy !== null || !stream.enabled}
                      aria-pressed={stream.force_fallback}
                      onClick={() => void run(stream.force_fallback ? 'Release fallback' : 'Lock fallback', () => client.streamControl(stream.enabled, !stream.force_fallback))}
                    >
                      {stream.force_fallback ? 'Return to stream' : 'Hold safety loop'}
                    </button>
                    <button
                      type="button"
                      className={styles.primaryButton}
                      disabled={demo || busy !== null || !stream.available}
                      onClick={() => void run(stream.enabled ? 'Stop stream' : 'Start stream', () => client.streamControl(!stream.enabled, false))}
                    >
                      {stream.enabled ? 'Stop MRT2' : 'Start MRT2'}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className={styles.primaryButton}
                    disabled={demo || busy !== null || !hasPreparedFallback}
                    onClick={() => void startPerformance()}
                  >
                    {busy === 'Start performance' ? 'Starting audio…' : 'Start performance'}
                  </button>
                )}
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={demo || busy !== null}
                  aria-label="Prepare next deck"
                  onClick={() => void run('Prepare next deck', () => client.prepareNext())}
                >
                  {busy === 'Prepare next deck' ? 'Preparing locally…' : 'Prepare next'}
                </button>
              </div>
            </div>

            {!stream.available ? <p className={styles.absent}>MRT2 is unavailable; the safety loop can still play.</p> : null}
            {!runtimeRunning && !hasPreparedFallback ? <p className={styles.absent}>Prepare safety deck A in Pre-set before starting audio.</p> : null}

            <MorphField
              prompts={stream.prompts}
              draftWeights={weights}
              disabled={demo || !runtimeRunning || !stream.enabled}
              busy={busy !== null}
              onFocus={(slot) => void focusLane(slot)}
            />

            <div className={styles.performanceFoot}>
              <label className={styles.morphTime}>
                <span>Movement time</span>
                <span className={styles.numberInput}>
                  <input className="mono" type="number" min={0} max={600} step={1} value={morphSeconds} onChange={(event) => setMorphSeconds(Number(event.target.value))} />
                  <span>sec</span>
                </span>
              </label>
              <p>{busy ? busy : stream.enabled ? 'Choose a direction. The blend will travel there without stopping.' : 'The prompt field wakes when the continuous stream is running.'}</p>
              <button type="button" className={styles.secondaryButton} onClick={() => setRoomView('shape')}>Edit directions</button>
            </div>
          </main>
        ) : null}

        {roomView === 'shape' ? <section className={styles.streamDesk} aria-labelledby="stream-heading">
          <div className={styles.sectionHead}>
            <div>
              <h2 id="stream-heading">Continuous engine</h2>
              <p>
                Six prompt lanes blend one uninterrupted MRT2 performance. The looped deck stays
                underneath as the safety floor.
              </p>
            </div>
            <div className={styles.engineActions}>
              <button
                type="button"
                className={styles.secondaryButton}
                disabled={demo || busy !== null || !runtimeRunning || !stream.enabled}
                aria-pressed={stream.force_fallback}
                onClick={() =>
                  void run(stream.force_fallback ? 'Release fallback' : 'Lock fallback', () =>
                    client.streamControl(stream.enabled, !stream.force_fallback),
                  )
                }
              >
                {stream.force_fallback ? 'Release fallback' : 'Lock fallback'}
              </button>
              {runtimeRunning ? (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={demo || busy !== null || !stream.available}
                  onClick={() =>
                    void run(stream.enabled ? 'Stop stream' : 'Start stream', () =>
                      client.streamControl(!stream.enabled, false),
                    )
                  }
                >
                  {busy === 'Start stream'
                    ? 'Starting…'
                    : stream.enabled
                      ? 'Stop stream'
                      : 'Start stream'}
                </button>
              ) : (
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={demo || busy !== null || !hasPreparedFallback}
                  onClick={() => void startPerformance()}
                >
                  {busy === 'Start performance' ? 'Starting audio…' : 'Start performance'}
                </button>
              )}
            </div>
          </div>

          {!stream.available ? (
            <p className={styles.absent} role="status">
              MRT2 is not installed. The fallback deck remains available; install the local engine
              before starting the stream.
            </p>
          ) : null}

          {!runtimeRunning && !hasPreparedFallback ? (
            <p className={styles.absent} role="status">
              Prepare safety deck A in Pre-set before starting audio.
            </p>
          ) : null}

          <div className={styles.lanes} aria-label="Prompt blend lanes">
            {stream.prompts.map((lane, index) => (
              <article className={styles.lane} key={lane.slot} data-active={(weights[index] ?? 0) > 0}>
                <div className={styles.laneNumber} aria-hidden="true">
                  {String(lane.slot + 1).padStart(2, '0')}
                </div>
                <label className={styles.promptField}>
                  <span>Prompt lane {lane.slot + 1}</span>
                  <input
                    value={prompts[index] ?? ''}
                    placeholder="Describe a musical direction"
                    maxLength={1000}
                    onChange={(event) => {
                      const next = [...prompts]
                      next[index] = event.target.value
                      setPrompts(next)
                      setDirtyPrompts((current) => new Set(current).add(index))
                    }}
                  />
                </label>
                <label className={styles.weightField}>
                  <span>Weight</span>
                  <input
                    type="range"
                    aria-label={`Prompt lane ${lane.slot + 1} weight`}
                    min={0}
                    max={1}
                    step={0.01}
                    value={weights[index] ?? 0}
                    onChange={(event) => {
                      const next = [...weights]
                      next[index] = Number(event.target.value)
                      setWeights(next)
                      setDirtyWeights((current) => new Set(current).add(index))
                    }}
                  />
                  <output className="mono">{Math.round((weights[index] ?? 0) * 100)}%</output>
                </label>
                <div className={styles.laneActions}>
                  <button
                    type="button"
                    aria-label={`Load prompt ${lane.slot + 1}`}
                    disabled={demo || busy !== null || !(prompts[index] ?? '').trim()}
                    onClick={() => void run(
                      `Load prompt ${lane.slot + 1}`,
                      () => client.streamPrompt(
                        lane.slot,
                        (prompts[index] ?? '').trim(),
                        weights[index] ?? 0,
                      ),
                      () => {
                        setDirtyPrompts((current) => {
                          const next = new Set(current)
                          next.delete(index)
                          return next
                        })
                        setDirtyWeights((current) => {
                          const next = new Set(current)
                          next.delete(index)
                          return next
                        })
                      },
                    )}
                  >
                    Load prompt
                  </button>
                  <button
                    type="button"
                    aria-label={`Morph lane ${lane.slot + 1} now`}
                    disabled={demo || busy !== null || !runtimeRunning || !stream.enabled}
                    onClick={() => void run(
                      `Morph lane ${lane.slot + 1}`,
                      () => client.streamWeight(lane.slot, weights[index] ?? 0, morphSeconds),
                      () => setDirtyWeights((current) => {
                        const next = new Set(current)
                        next.delete(index)
                        return next
                      }),
                    )}
                  >
                    Morph now
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className={styles.utilities}>
            <fieldset className={styles.utility}>
              <legend>Live morph</legend>
              <label>
                <span>Duration</span>
                <span className={styles.numberInput}>
                  <input
                    className="mono"
                    type="number"
                    min={0}
                    max={600}
                    step={1}
                    value={morphSeconds}
                    onChange={(event) => setMorphSeconds(Number(event.target.value))}
                  />
                  <span>sec</span>
                </span>
              </label>
              <p>Used by every “Morph now” action above.</p>
            </fieldset>

            <fieldset className={styles.utility}>
              <legend>Phrase schedule</legend>
              <div className={styles.compactFields}>
                <label>
                  <span>Lane</span>
                  <select value={scheduleSlot} onChange={(event) => setScheduleSlot(Number(event.target.value))}>
                    {stream.prompts.map((lane) => <option key={lane.slot} value={lane.slot}>{lane.slot + 1}</option>)}
                  </select>
                </label>
                <label>
                  <span>Target</span>
                  <input type="number" min={0} max={1} step={0.05} value={scheduleWeight} onChange={(event) => setScheduleWeight(Number(event.target.value))} />
                </label>
                <label>
                  <span>Next phrase</span>
                  <select value={phraseBars} onChange={(event) => setPhraseBars(Number(event.target.value) as PhraseBars)}>
                    {[4, 8, 16, 32].map((bars) => <option key={bars} value={bars}>{bars} bars</option>)}
                  </select>
                </label>
                <label>
                  <span>Morph over</span>
                  <input type="number" min={0.25} max={128} step={0.25} value={morphBars} onChange={(event) => setMorphBars(Number(event.target.value))} />
                </label>
              </div>
              {snapshot.agent.running ? (
                <button
                  type="button"
                  disabled={demo || busy !== null || !runtimeRunning}
                  onClick={() => void run('Schedule stream morph', () => client.streamSchedule(scheduleSlot, scheduleWeight, phraseBars, morphBars))}
                >
                  Schedule musical intent
                </button>
              ) : (
                <button
                  type="button"
                  disabled={demo || busy !== null || !runtimeRunning}
                  onClick={() => void run('Start scheduling agent', () => client.startAgent(false))}
                >
                  Start phrase scheduling
                </button>
              )}
              {!snapshot.agent.running ? (
                <p>The local scheduling agent is stopped. Starting it does not touch audio.</p>
              ) : null}
            </fieldset>

            <fieldset className={styles.utility}>
              <legend>Generation character</legend>
              <div className={styles.compactFields}>
                <label>
                  <span>Temperature</span>
                  <input
                    type="number"
                    min={0.1}
                    max={4}
                    step={0.1}
                    value={temperature}
                    onChange={(event) => {
                      setTemperature(Number(event.target.value))
                      setDirtyTemperature(true)
                    }}
                  />
                </label>
                <label>
                  <span>Top K</span>
                  <input
                    type="number"
                    min={1}
                    max={2048}
                    step={1}
                    value={topK}
                    onChange={(event) => {
                      setTopK(Number(event.target.value))
                      setDirtyTopK(true)
                    }}
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={demo || busy !== null}
                onClick={() => void run(
                  'Update stream settings',
                  () => client.streamSettings(temperature, topK),
                  () => {
                    setDirtyTemperature(false)
                    setDirtyTopK(false)
                  },
                )}
              >
                Apply settings
              </button>
            </fieldset>
          </div>
        </section> : null}

        {roomView === 'codex' ? <aside className={styles.codexDesk} aria-labelledby="codex-heading">
          <div className={styles.sectionHead}>
            <div>
              <h2 id="codex-heading">Codex thread</h2>
              <p>A local coding collaborator for this project. It never enters the audio path.</p>
            </div>
            <div className={styles.bridgeMeta}>
              <span className={styles.processState} data-running={snapshot.codex_bridge.running}>
                {snapshot.codex_bridge.running ? 'Bridge ready' : 'Bridge stopped'}
              </span>
              {snapshot.codex_bridge.running ? (
                <button
                  type="button"
                  disabled={demo || busy !== null}
                  onClick={() => void run('Stop Codex bridge', () => client.stopCodex())}
                >
                  Stop bridge
                </button>
              ) : null}
            </div>
          </div>

          {!snapshot.codex_bridge.running ? (
            <div className={styles.bridgeStart}>
              <p>
                Start the project bridge to create or attach a Codex thread without opening a
                terminal.
              </p>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={demo || busy !== null || !snapshot.codex_bridge.available}
                onClick={() => void run('Start Codex bridge', () => client.startCodex())}
              >
                {busy === 'Start Codex bridge' ? 'Starting bridge…' : 'Start local bridge'}
              </button>
            </div>
          ) : (
            <>
              <div className={styles.threadStatus}>
                <span>Attached thread</span>
                <strong>{codex.thread_id ? codex.thread_id.slice(0, 13) : 'none'}</strong>
                <span className="mono">{codex.turn_status}</span>
              </div>

              <div className={styles.threadTools}>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => {
                    setCreatingThread(true)
                    setPrompt('')
                    setModel('')
                  }}
                >
                  New thread
                </button>
                <button type="button" disabled={busy !== null} onClick={() => void refreshThreads()}>
                  Refresh list
                </button>
                <button type="button" disabled={busy !== null || !codex.thread_id} onClick={() => void readThread()}>
                  Refresh thread
                </button>
                <button
                  type="button"
                  disabled={busy !== null || !activeTurn}
                  onClick={() => void run('Interrupt Codex turn', () => client.interruptCodexTurn())}
                >
                  Interrupt turn
                </button>
              </div>

              <section className={styles.threadBrowser} aria-labelledby="recent-threads">
                <h3 id="recent-threads">Recent project threads</h3>
                {threads.length === 0 ? (
                  <p className={styles.empty}>No project threads returned. Refresh, or start one below.</p>
                ) : (
                  <ul>
                    {threads.slice(0, 8).map((thread) => (
                      <li key={thread.id} data-attached={thread.id === codex.thread_id}>
                        <button
                          type="button"
                          disabled={busy !== null || thread.id === codex.thread_id}
                          onClick={async () => {
                            const value = await run('Attach Codex thread', () => client.resumeCodexThread(thread.id))
                            if (value) setThreadDetail(value)
                          }}
                        >
                          <span>{threadTitle(thread)}</span>
                          <small>
                            {thread.id === codex.thread_id ? 'Attached' : displayTime(thread.updatedAt) ?? thread.id.slice(0, 8)}
                          </small>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {codex.thread_id ? (
                <section className={styles.transcript} aria-labelledby="thread-transcript">
                  <h3 id="thread-transcript">Thread activity</h3>
                  {transcript.length === 0 ? (
                    <p className={styles.empty}>No readable messages yet. Send a direction to begin.</p>
                  ) : (
                    <ol>
                      {transcript.map((line) => (
                        <li key={line.id}>
                          <span>{line.role}</span>
                          <p>{line.text}</p>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              ) : null}

              <form
                className={styles.composer}
                onSubmit={codex.thread_id && !creatingThread ? sendDirection : startThread}
              >
                <label htmlFor="codex-direction">
                  {codex.thread_id && !creatingThread ? 'Direct this thread' : 'Start a new thread'}
                </label>
                <textarea
                  id="codex-direction"
                  rows={4}
                  maxLength={8000}
                  value={prompt}
                  placeholder={
                    codex.thread_id && !creatingThread
                      ? 'What should Codex inspect or change?'
                      : 'Describe the first task (optional)'
                  }
                  onChange={(event) => setPrompt(event.target.value)}
                />
                {!codex.thread_id || creatingThread ? (
                  <label className={styles.modelField}>
                    <span>Model override <em>optional</em></span>
                    {models.length > 0 ? (
                      <select value={model} onChange={(event) => setModel(event.target.value)}>
                        <option value="">Use Codex default</option>
                        {models.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.displayName ?? item.id}{item.isDefault ? ' · default' : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input value={model} maxLength={100} placeholder="Use Codex default" onChange={(event) => setModel(event.target.value)} />
                    )}
                  </label>
                ) : null}
                <div className={styles.composerFoot}>
                  <p>
                    {codex.thread_id && !creatingThread
                      ? activeTurn
                        ? 'Steer adds direction to the running turn; interrupt stops it.'
                        : 'A new turn runs in this repository with local workspace access.'
                      : codex.thread_id
                        ? 'The new thread will replace the current session attachment.'
                        : 'The thread is attached to the current DJ session.'}
                  </p>
                  <div className={styles.composerActions}>
                    {creatingThread ? (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        disabled={busy !== null}
                        onClick={() => setCreatingThread(false)}
                      >
                        Cancel
                      </button>
                    ) : null}
                    {codex.thread_id && !creatingThread ? (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        disabled={demo || busy !== null || !activeTurn || !prompt.trim()}
                        onClick={() => void steerDirection()}
                      >
                        {busy === 'Steer active Codex turn' ? 'Steering…' : 'Steer active turn'}
                      </button>
                    ) : null}
                    <button
                      type="submit"
                      className={styles.primaryButton}
                      disabled={
                        demo ||
                        busy !== null ||
                        (Boolean(codex.thread_id) &&
                          !creatingThread &&
                          (!prompt.trim() || activeTurn))
                      }
                    >
                      {busy === 'Send direction to Codex'
                        ? 'Sending…'
                        : codex.thread_id && !creatingThread
                          ? 'Send new turn'
                          : 'Start thread'}
                    </button>
                  </div>
                </div>
              </form>
            </>
          )}
        </aside> : null}
      </div>
    </div>
  )
}
