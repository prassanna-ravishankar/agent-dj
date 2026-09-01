/**
 * One reducer over the typed adapter. No state library.
 *
 * The reducer holds only what the browser legitimately owns: the last snapshot it read, the
 * request lifecycle, and view-local focus. It never holds system state of record — that lives
 * in sessions/ and is re-read, never reconstructed here.
 */

import type { AdapterError, DeckName, FeedbackKind, Snapshot } from '../adapter/types'

export type LoadPhase = 'idle' | 'loading' | 'ready' | 'unavailable'

export interface AppState {
  phase: LoadPhase
  snapshot: Snapshot | null
  error: AdapterError | null
  /** Feedback awaiting confirmation from the control plane. */
  pendingFeedback: FeedbackKind | null
  /** Last command error, surfaced inline rather than as a toast. */
  commandError: AdapterError | null
  focusedDeck: DeckName
  /** Announcements for the ARIA live region. */
  announcement: string
}

export const initialState: AppState = {
  phase: 'idle',
  snapshot: null,
  error: null,
  pendingFeedback: null,
  commandError: null,
  focusedDeck: 'A',
  announcement: '',
}

export type Action =
  | { type: 'load/start' }
  | { type: 'load/ok'; snapshot: Snapshot }
  | { type: 'load/fail'; error: AdapterError }
  | { type: 'feedback/pending'; kind: FeedbackKind }
  | { type: 'feedback/settled' }
  | { type: 'command/fail'; error: AdapterError }
  | { type: 'command/clear' }
  | { type: 'deck/focus'; deck: DeckName }
  | { type: 'announce'; message: string }

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'load/start':
      return { ...state, phase: state.snapshot ? state.phase : 'loading' }

    case 'load/ok':
      return { ...state, phase: 'ready', snapshot: action.snapshot, error: null }

    case 'load/fail':
      return { ...state, phase: 'unavailable', error: action.error }

    case 'feedback/pending':
      return { ...state, pendingFeedback: action.kind, commandError: null }

    case 'feedback/settled':
      return { ...state, pendingFeedback: null }

    case 'command/fail':
      return { ...state, commandError: action.error, pendingFeedback: null }

    case 'command/clear':
      return { ...state, commandError: null }

    case 'deck/focus':
      return { ...state, focusedDeck: action.deck }

    case 'announce':
      return { ...state, announcement: action.message }

    default:
      return state
  }
}
