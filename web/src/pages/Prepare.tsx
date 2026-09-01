/**
 * Pre-set view — the desk-at-rest mode. Calmer and denser than the console.
 *
 * Generation is slow and fallible and lives entirely off the audio path, so it belongs here
 * rather than competing for attention during a set.
 */

import { useState } from 'react'
import type { DeckName, Snapshot } from '../adapter/types'
import styles from './Prepare.module.css'

interface Props {
  snapshot: Snapshot
  demo: boolean
  pendingCommand: string | null
  onGenerate: (deck: DeckName, prompt: string, bpm: number, duration: number) => void
  onRuntime: (action: 'start' | 'stop', testMode: boolean) => void
  onAgent: (action: 'start' | 'stop', testMode: boolean) => void
}

export function Prepare({ snapshot, demo, pendingCommand, onGenerate, onRuntime, onAgent }: Props) {
  const [deck, setDeck] = useState<DeckName>('A')
  const [prompt, setPrompt] = useState('warm groovy house, percussion-forward, patient')
  const [bpm, setBpm] = useState(124)
  const [duration, setDuration] = useState(16)

  const { runtime, agent, state } = snapshot

  return (
    <div className={styles.prepare}>
      <section className={styles.panel} aria-label="Processes">
        <h2 className={`label ${styles.heading}`}>Processes</h2>
        <dl className={styles.facts}>
          <div className={styles.fact}>
            <dt>Runtime</dt>
            <dd data-state={runtime.running ? 'running' : 'absent'}>
              {runtime.running ? `running · pid ${runtime.pid}` : 'not running'}
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>Agent</dt>
            <dd data-state={agent.running ? 'running' : 'absent'}>
              {agent.running ? `running · pid ${agent.pid}` : 'not running'}
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>Session</dt>
            <dd className="mono">{state.session_id}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Status</dt>
            <dd className="mono">{state.status}</dd>
          </div>
        </dl>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.button}
            disabled={demo || pendingCommand !== null}
            onClick={() => onRuntime(runtime.running ? 'stop' : 'start', false)}
          >
            {pendingCommand === 'Runtime start'
              ? 'Starting runtime…'
              : runtime.running
                ? 'Stop runtime'
                : 'Start runtime'}
          </button>
          <button
            type="button"
            className={styles.button}
            disabled={demo || pendingCommand !== null}
            onClick={() => onAgent(agent.running ? 'stop' : 'start', false)}
          >
            {pendingCommand === 'Agent start'
              ? 'Starting agent…'
              : agent.running
                ? 'Stop agent'
                : 'Start agent'}
          </button>
        </div>
        <p className={styles.note}>
          Starting live audio requires at least one prepared deck. Stopping the agent is safe —
          audio continues on the current deck.
        </p>
      </section>

      <section className={styles.panel} aria-label="Generate material">
        <h2 className={`label ${styles.heading}`}>Generate</h2>
        <div className={styles.field}>
          <label className={`label ${styles.fieldLabel}`} htmlFor="gen-deck">
            Deck
          </label>
          <select
            id="gen-deck"
            className={styles.select}
            value={deck}
            onChange={(e) => setDeck(e.target.value as DeckName)}
          >
            <option value="A">A</option>
            <option value="B">B</option>
          </select>
        </div>
        <div className={styles.field}>
          <label className={`label ${styles.fieldLabel}`} htmlFor="gen-prompt">
            Prompt
          </label>
          <textarea
            id="gen-prompt"
            className={styles.textarea}
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={`label ${styles.fieldLabel}`} htmlFor="gen-bpm">
              BPM
            </label>
            <input
              id="gen-bpm"
              className={`mono ${styles.input}`}
              type="number"
              min={40}
              max={240}
              value={bpm}
              onChange={(e) => setBpm(Number(e.target.value))}
            />
          </div>
          <div className={styles.field}>
            <label className={`label ${styles.fieldLabel}`} htmlFor="gen-duration">
              Duration (s)
            </label>
            <input
              id="gen-duration"
              className={`mono ${styles.input}`}
              type="number"
              min={2}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            />
          </div>
        </div>
        <button
          type="button"
          className={styles.button}
          disabled={demo || pendingCommand !== null || prompt.trim().length === 0}
          onClick={() => onGenerate(deck, prompt.trim(), bpm, duration)}
        >
          {pendingCommand === `Generate deck ${deck}`
            ? `Generating deck ${deck}…`
            : `Generate onto deck ${deck}`}
        </button>
        <p className={styles.note}>
          Generation runs locally and is slower than playback. It never touches the audio
          callback, so a failure here cannot stop the music.
        </p>
      </section>

      <section className={styles.panel} aria-label="Decks">
        <h2 className={`label ${styles.heading}`}>Decks</h2>
        {(['A', 'B'] as const).map((name) => {
          const d = state.decks[name]
          return (
            <div key={name} className={styles.deckRow}>
              <span className={styles.deckName}>{name}</span>
              <span className={styles.deckStatus} data-status={d.status}>
                {d.status}
              </span>
              <span className={styles.deckPrompt}>
                {d.prompt ?? <em className={styles.absent}>nothing prepared</em>}
              </span>
            </div>
          )
        })}
      </section>
    </div>
  )
}
