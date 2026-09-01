/**
 * Agent DJ — local performance console.
 *
 * The browser is a control and observation surface. It holds no system state of record,
 * performs no audio work, and cannot break the music. When the local control server is
 * absent it says so plainly rather than pretending.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { createLiveClient } from './adapter/client'
import type { DeckName, FeedbackKind, FilterKind } from './adapter/types'
import { consequenceFor } from './adapter/policy'
import { nextPhraseBar } from './adapter/clock'
import { buildScenario, SCENARIOS, type ScenarioId } from './demo/fixtures'
import { initialState, reducer } from './state/store'
import { selectView } from './state/selectors'
import { TopEdge } from './components/TopEdge'
import { Horizon } from './components/Horizon'
import { Decks } from './components/Decks'
import { GestureRow } from './components/GestureRow'
import { Controls } from './components/Controls'
import { Chain } from './components/Chain'
import { Prepare } from './pages/Prepare'
import { ShortcutOverlay } from './components/ShortcutOverlay'
import styles from './App.module.css'

const client = createLiveClient()

type Route = 'console' | 'prepare'

function readDemoFlag(): boolean {
  if (typeof window === 'undefined') return __DEMO_DEFAULT__
  const params = new URLSearchParams(window.location.search)
  if (params.has('demo')) return params.get('demo') !== 'false'
  return __DEMO_DEFAULT__
}

function readScenario(): ScenarioId {
  if (typeof window === 'undefined') return 'live-safe'
  const params = new URLSearchParams(window.location.search)
  const value = params.get('scenario')
  return (SCENARIOS.find((s) => s.id === value)?.id ?? 'live-safe') as ScenarioId
}

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [demo] = useState(readDemoFlag)
  const [scenario, setScenario] = useState<ScenarioId>(readScenario)
  const [route, setRoute] = useState<Route>('console')
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [tick, setTick] = useState(0)
  const chainRef = useRef<HTMLDivElement>(null)

  // Demo mode is an explicit, separately marked source. It never masks a live failure.
  const load = useCallback(async () => {
    if (demo) {
      dispatch({ type: 'load/ok', snapshot: buildScenario(scenario) })
      return
    }
    dispatch({ type: 'load/start' })
    const result = await client.snapshot()
    if (result.ok) dispatch({ type: 'load/ok', snapshot: result.value })
    else dispatch({ type: 'load/fail', error: result.error })
  }, [demo, scenario])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (demo) return
    return client.subscribe(() => void load())
  }, [demo, load])

  // Advance the derived clock. Under reduced motion this steps rather than sweeps, and the
  // horizon stops scrolling — see tokens.css and Horizon.module.css.
  useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const period = reduced ? 1_935 : 250
    const timer = window.setInterval(() => setTick((t) => t + 1), period)
    return () => window.clearInterval(timer)
  }, [])

  const snapshot = state.snapshot
  const view = useMemo(
    () => (snapshot ? selectView(snapshot, Date.now()) : null),
    // `tick` intentionally participates: the clock is derived from wall time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [snapshot, tick],
  )

  const announce = useCallback((message: string) => {
    dispatch({ type: 'announce', message })
  }, [])

  const run = useCallback(
    async (label: string, action: () => Promise<{ ok: boolean; error?: unknown }>) => {
      if (demo) {
        announce(`${label} is unavailable in demo mode.`)
        return
      }
      const result = await action()
      if (!result.ok && result.error) {
        dispatch({ type: 'command/fail', error: result.error as never })
        announce(`${label} failed.`)
      } else {
        announce(`${label} accepted.`)
        void load()
      }
    },
    [announce, demo, load],
  )

  const onFeedback = useCallback(
    (kind: FeedbackKind) => {
      const c = consequenceFor(kind)
      dispatch({ type: 'feedback/pending', kind })

      // Preview: where this intent will land, in bars. Python decides for real; this is the
      // mirrored policy table used only to place the ghost tick.
      const bar = view?.clock.bar
      const landing = bar !== null && bar !== undefined ? nextPhraseBar(bar, 4) : null
      announce(
        landing !== null
          ? `${c.label} sent. Lands at bar ${landing}, over ${c.bars} bars.`
          : `${c.label} sent. Landing bar unavailable while the clock is uncertain.`,
      )

      if (demo) {
        window.setTimeout(() => dispatch({ type: 'feedback/settled' }), 1200)
        return
      }
      void client.feedback(kind).then((result) => {
        if (!result.ok) dispatch({ type: 'command/fail', error: result.error })
        else {
          dispatch({ type: 'feedback/settled' })
          void load()
        }
      })
    },
    [announce, demo, load, view],
  )

  const focusDeck = useCallback((deck: DeckName) => dispatch({ type: 'deck/focus', deck }), [])

  // Keyboard model. Ignored while typing so prompt entry is unaffected.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return

      const key = event.key.toLowerCase()

      if (event.key === '?') {
        event.preventDefault()
        setShowShortcuts((v) => !v)
        return
      }
      if (event.key === 'Escape') {
        setShowShortcuts(false)
        return
      }
      if (key === '/') {
        event.preventDefault()
        chainRef.current?.focus()
        return
      }
      const digit = FEEDBACK_KEYS[event.key]
      if (digit) {
        event.preventDefault()
        onFeedback(digit)
        return
      }
      if (key === 'a' || key === 'b') {
        event.preventDefault()
        focusDeck(key.toUpperCase() as DeckName)
        return
      }
      if (event.code === 'Space') {
        event.preventDefault()
        void run(`Play deck ${state.focusedDeck}`, () => client.play(state.focusedDeck))
        return
      }
      if (key === 'r') {
        event.preventDefault()
        const action = view?.recording ? 'stop' : 'start'
        if (window.confirm(`${action === 'start' ? 'Start' : 'Stop'} master recording?`)) {
          void run(`Recording ${action}`, () => client.record(action))
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [focusDeck, onFeedback, run, state.focusedDeck, view])

  if (state.phase === 'loading' || (!snapshot && state.phase === 'idle')) {
    return (
      <div className={styles.centered} role="status">
        <p className={styles.centeredTitle}>Reading session state…</p>
      </div>
    )
  }

  if (!snapshot || !view) {
    return (
      <div className={styles.centered} data-state="offline">
        <div className={styles.unavailable}>
          <h1 className={styles.centeredTitle}>Local control server unavailable</h1>
          <p className={styles.centeredBody}>
            {state.error?.message ?? 'The browser could not reach the local control server.'} This
            surface is observation-only: audio, if it is running, is unaffected.
          </p>
          <p className={styles.centeredBody}>
            Start the local server, or open{' '}
            <a className={styles.link} href="?demo=true">
              demo mode
            </a>{' '}
            to review the interface with fixture data.
          </p>
          <button type="button" className={styles.retry} onClick={() => void load()}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  const { state: dj } = snapshot

  return (
    <div className={styles.app}>
      <a className={styles.skip} href="#main">
        Skip to console
      </a>

      <TopEdge
        runtime={snapshot.runtime}
        agent={snapshot.agent}
        recording={view.recording}
        sessionId={dj.session_id}
        demo={snapshot.demo}
      />

      {snapshot.demo ? (
        <div className={styles.demoBar} data-state="demo">
          <span className={styles.demoTag}>DEMO DATA</span>
          <label className={styles.demoLabel}>
            Scenario
            <select
              className={styles.demoSelect}
              value={scenario}
              onChange={(e) => setScenario(e.target.value as ScenarioId)}
            >
              {SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <span className={styles.demoNote}>
            {SCENARIOS.find((s) => s.id === scenario)?.note}
          </span>
        </div>
      ) : null}

      <nav className={styles.nav} aria-label="Views">
        <button
          type="button"
          className={styles.navItem}
          data-active={route === 'console' ? 'true' : 'false'}
          onClick={() => setRoute('console')}
        >
          Console
        </button>
        <button
          type="button"
          className={styles.navItem}
          data-active={route === 'prepare' ? 'true' : 'false'}
          onClick={() => setRoute('prepare')}
        >
          Pre-set
        </button>
      </nav>

      {state.commandError ? (
        <p className={styles.commandError} role="alert">
          {state.commandError.message}
          {state.commandError.detail ? ` ${state.commandError.detail}` : ''}
          <button
            type="button"
            className={styles.dismiss}
            onClick={() => dispatch({ type: 'command/clear' })}
          >
            Dismiss
          </button>
        </p>
      ) : null}

      <main id="main" className={styles.main}>
        {route === 'prepare' ? (
          <Prepare
            snapshot={snapshot}
            demo={snapshot.demo}
            onGenerate={(deck, prompt, bpm, duration) =>
              run(`Generate deck ${deck}`, () => client.generate(deck, prompt, bpm, duration))
            }
            onRuntime={(action, testMode) =>
              run(`Runtime ${action}`, () =>
                action === 'start' ? client.startRuntime(testMode) : client.stopRuntime(),
              )
            }
            onAgent={(action, testMode) =>
              run(`Agent ${action}`, () =>
                action === 'start' ? client.startAgent(testMode) : client.stopAgent(),
              )
            }
          />
        ) : (
          <div className={styles.console}>
            <div className={styles.stack}>
              <Horizon
                clock={view.clock}
                coverage={view.coverage}
                inFlight={view.pending ? [view.pending] : []}
                runtimeRunning={snapshot.runtime.running}
              />
              <Decks
                decks={dj.decks}
                onAir={view.onAir}
                pending={view.pending}
                seamProgress={view.seamProgress}
                barsUntilLanding={view.barsUntilLanding}
                focused={state.focusedDeck}
                onFocus={focusDeck}
              />
              <Controls
                decks={dj.decks}
                master={dj.master}
                focused={state.focusedDeck}
                onFocus={focusDeck}
                recording={view.recording}
                runtimeRunning={snapshot.runtime.running}
                onCrossfade={(target, bars) =>
                  run(`Crossfade to ${target}`, () => client.crossfade(target, bars))
                }
                onPlay={(deck) => run(`Play deck ${deck}`, () => client.play(deck))}
                onGain={(deck, gainDb) =>
                  run(`Gain deck ${deck}`, () => client.gain(deck, gainDb))
                }
                onFilter={(deck, kind: FilterKind, hz) =>
                  run(`Filter deck ${deck}`, () => client.filter(deck, kind, hz))
                }
                onRecord={(action) => run(`Recording ${action}`, () => client.record(action))}
              />
              <GestureRow
                onFeedback={onFeedback}
                pendingKind={state.pendingFeedback}
                disabled={!snapshot.runtime.running}
                disabledReason={
                  snapshot.runtime.running
                    ? null
                    : 'Runtime is offline — feedback needs a running session.'
                }
              />
            </div>
            <div className={styles.rail} ref={chainRef} tabIndex={-1}>
              <Chain entities={view.chain} />
            </div>
          </div>
        )}
      </main>

      {/* Polite by default. Critical coverage and generation failure are assertive. */}
      <p className="visually-hidden" aria-live="polite" aria-atomic="true">
        {state.announcement}
      </p>
      <p className="visually-hidden" aria-live="assertive" aria-atomic="true">
        {view.coverage.level === 'critical'
          ? 'Future coverage critical. Extend coverage now.'
          : dj.decks.A.status === 'failed' || dj.decks.B.status === 'failed'
            ? 'Generation failed. The other deck continues.'
            : ''}
      </p>

      {showShortcuts ? <ShortcutOverlay onClose={() => setShowShortcuts(false)} /> : null}
    </div>
  )
}

const FEEDBACK_KEYS: Record<string, FeedbackKind | undefined> = {
  '1': 'love',
  '2': 'dislike',
  '3': 'more-energy',
  '4': 'less-energy',
  '5': 'boring',
  '6': 'weird',
}
