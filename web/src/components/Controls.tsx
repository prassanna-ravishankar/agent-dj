/**
 * Secondary controls: transport, crossfade, gain, filter, record, master readouts.
 *
 * Crossfade is a BAR-DENOMINATED COMMITMENT (4/8/16/32), never a draggable slider — bars are
 * the actual vocabulary. Gain and filter are steppers with typed entry: a slider would imply
 * precision and real-time responsiveness the OSC boundary does not promise.
 *
 * Master loudness renders as ghost cells. peak_dbfs and lufs_short are null in every recorded
 * session; metering is specified (PROJECT_SPEC.md 48) but not wired into state.
 */

import { useState } from 'react'
import type { DeckName, DeckState, FilterKind, MasterState } from '../adapter/types'
import { FILTER_KINDS } from '../adapter/types'
import { CROSSFADE_BARS } from '../adapter/policy'
import { SegmentReadout } from './SegmentReadout'
import styles from './Controls.module.css'

interface Props {
  decks: Record<DeckName, DeckState>
  master: MasterState
  focused: DeckName
  onFocus: (deck: DeckName) => void
  recording: boolean
  runtimeRunning: boolean
  onCrossfade: (target: DeckName, bars: number) => void
  onPlay: (deck: DeckName) => void
  onGain: (deck: DeckName, gainDb: number) => void
  onFilter: (deck: DeckName, kind: FilterKind, hz: number) => void
  onRecord: (action: 'start' | 'stop') => void
}

export function Controls({
  decks,
  master,
  focused,
  onFocus,
  recording,
  runtimeRunning,
  onCrossfade,
  onPlay,
  onGain,
  onFilter,
  onRecord,
}: Props) {
  const [filterKind, setFilterKind] = useState<FilterKind>('lowpass')
  const [hz, setHz] = useState(2200)
  const deck = decks[focused]
  const other: DeckName = focused === 'A' ? 'B' : 'A'
  const canPlay = runtimeRunning && deck.audio_path !== null

  return (
    <section className={styles.controls} aria-label="Transport and mixer">
      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Deck</span>
        <div className={styles.segmented} role="group" aria-label="Focused deck">
          {(['A', 'B'] as const).map((name) => (
            <button
              key={name}
              type="button"
              className={styles.segment}
              data-active={focused === name ? 'true' : 'false'}
              onClick={() => onFocus(name)}
              aria-pressed={focused === name}
              aria-keyshortcuts={name}
            >
              {name}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={styles.action}
          disabled={!canPlay}
          onClick={() => onPlay(focused)}
          title={
            canPlay
              ? `Bring deck ${focused} on air with a short safe fade`
              : `Deck ${focused} has no prepared audio`
          }
          aria-keyshortcuts="Space"
        >
          Play {focused}
        </button>
      </div>

      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Crossfade to {other}</span>
        <div className={styles.bars} role="group" aria-label={`Crossfade to deck ${other}`}>
          {CROSSFADE_BARS.map((bars) => (
            <button
              key={bars}
              type="button"
              className={styles.bar}
              disabled={!runtimeRunning}
              onClick={() => onCrossfade(other, bars)}
              title={`Crossfade to deck ${other} over ${bars} bars`}
            >
              <span className={`mono ${styles.barValue}`}>{bars}</span>
              <span className={styles.barUnit}>bars</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Gain {focused}</span>
        <div className={styles.stepper}>
          <button
            type="button"
            className={styles.step}
            disabled={!runtimeRunning}
            onClick={() => onGain(focused, Math.max(-60, deck.gain_db - 1))}
            aria-label={`Decrease deck ${focused} gain by 1 decibel`}
          >
            −
          </button>
          <SegmentReadout
            value={deck.gain_db}
            cells={3}
            unit="dB"
            size="sm"
            tone={deck.status === 'playing' ? 'amber' : 'slate'}
            decimals={0}
          />
          <button
            type="button"
            className={styles.step}
            disabled={!runtimeRunning}
            onClick={() => onGain(focused, Math.min(6, deck.gain_db + 1))}
            aria-label={`Increase deck ${focused} gain by 1 decibel`}
          >
            +
          </button>
        </div>
      </div>

      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Filter {focused}</span>
        <div className={styles.filter}>
          <select
            className={styles.select}
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value as FilterKind)}
            aria-label="Filter kind"
          >
            {FILTER_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
          <input
            className={`mono ${styles.hz}`}
            type="number"
            min={20}
            max={20000}
            step={10}
            value={hz}
            onChange={(e) => setHz(Number(e.target.value))}
            aria-label="Filter frequency in hertz"
          />
          <button
            type="button"
            className={styles.action}
            disabled={!runtimeRunning || !Number.isFinite(hz) || hz <= 0}
            onClick={() => onFilter(focused, filterKind, hz)}
          >
            Apply
          </button>
        </div>
      </div>

      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Master</span>
        <div className={styles.master}>
          {/* Always ghosted today — metering is not wired into state. */}
          <SegmentReadout
            value={master.peak_dbfs}
            cells={4}
            label="Peak"
            unit="dBFS"
            size="sm"
            tone="ink"
            unavailableText="peak metering unavailable"
            decimals={1}
          />
          <SegmentReadout
            value={master.lufs_short}
            cells={4}
            label="LUFS"
            size="sm"
            tone="ink"
            unavailableText="loudness metering unavailable"
            decimals={1}
          />
        </div>
        <p className={styles.masterNote}>metering not wired into state</p>
      </div>

      <div className={styles.group}>
        <span className={`label ${styles.groupLabel}`}>Record</span>
        <button
          type="button"
          className={styles.record}
          data-state={recording ? 'recording' : 'idle'}
          disabled={!runtimeRunning}
          onClick={() => onRecord(recording ? 'stop' : 'start')}
          aria-keyshortcuts="R"
        >
          <span className={styles.recordMark} aria-hidden="true" />
          {recording ? 'Stop recording' : 'Start recording'}
        </button>
      </div>
    </section>
  )
}
