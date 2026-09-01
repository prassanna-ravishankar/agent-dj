/**
 * The ONLY module that talks to the backend.
 *
 * Contract rules:
 *  - The UI never parses JSONL, never touches the filesystem, never builds a CLI string.
 *  - Exactly the actions PRODUCT.md 8 lists exist here. If `dj` does not expose it, there is
 *    no method for it, so the UI structurally cannot invent capability (PRODUCT.md 13.10).
 *  - Every method returns Result<T>. Nothing throws across this boundary.
 *  - When the integration server is absent, methods fail HONESTLY with code 'unavailable'.
 *    They never fall back to fixtures — demo mode is an explicit, separately marked source.
 *
 * The Python/FastAPI server implementing this contract is owned by Codex; see web/HANDOFF.md.
 */

import type {
  AdapterError,
  DeckName,
  DoctorReport,
  FeedbackKind,
  FilterKind,
  ProcessHealth,
  Result,
  Snapshot,
} from './types'
import { err, ok } from './types'

export const API_BASE = '/api'

export interface DJClient {
  snapshot(): Promise<Result<Snapshot>>
  doctor(): Promise<Result<DoctorReport>>
  startRuntime(testMode: boolean): Promise<Result<ProcessHealth>>
  stopRuntime(): Promise<Result<ProcessHealth>>
  startAgent(testMode: boolean): Promise<Result<ProcessHealth>>
  stopAgent(): Promise<Result<ProcessHealth>>
  generate(deck: DeckName, prompt: string, bpm: number, duration: number): Promise<Result<void>>
  play(deck: DeckName): Promise<Result<void>>
  crossfade(target: DeckName, bars: number): Promise<Result<void>>
  gain(deck: DeckName, gainDb: number): Promise<Result<void>>
  filter(deck: DeckName, kind: FilterKind, frequencyHz: number): Promise<Result<void>>
  record(action: 'start' | 'stop'): Promise<Result<void>>
  feedback(kind: FeedbackKind): Promise<Result<void>>
  /** Server-sent events for state changes. Returns an unsubscribe function. */
  subscribe(onChange: () => void): () => void
}

const UNAVAILABLE: AdapterError = {
  code: 'unavailable',
  message: 'Local control server is not reachable.',
  detail:
    'The browser is a control surface only; audio is unaffected. Start the local server, or use demo mode.',
}

function describe(error: unknown): AdapterError {
  if (error instanceof Error && error.name === 'AbortError') {
    return { code: 'transport', message: 'Request timed out.' }
  }
  return { ...UNAVAILABLE, detail: error instanceof Error ? error.message : UNAVAILABLE.detail }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 10_000,
): Promise<Result<T>> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    })
    if (!response.ok) {
      let detail: string | undefined
      try {
        const body = (await response.json()) as { detail?: string; error?: string }
        detail = body.detail ?? body.error
      } catch {
        detail = undefined
      }
      const code = response.status === 409 ? 'refused' : response.status === 400 ? 'invalid' : 'transport'
      return err({
        code,
        message: `Command rejected (${response.status}).`,
        ...(detail ? { detail } : {}),
      })
    }
    if (response.status === 204) return ok(undefined as T)
    return ok((await response.json()) as T)
  } catch (error) {
    return err(describe(error))
  } finally {
    clearTimeout(timer)
  }
}

/** Live client against the local HTTP/SSE contract in web/HANDOFF.md. */
export function createLiveClient(): DJClient {
  const post = <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

  return {
    snapshot: () => request<Snapshot>('/snapshot'),
    doctor: () => request<DoctorReport>('/doctor'),
    startRuntime: (testMode) => post<ProcessHealth>('/runtime/start', { test_mode: testMode }),
    stopRuntime: () => post<ProcessHealth>('/runtime/stop'),
    startAgent: (testMode) => post<ProcessHealth>('/agent/start', { test_mode: testMode }),
    stopAgent: () => post<ProcessHealth>('/agent/stop'),
    generate: (deck, prompt, bpm, duration) =>
      post<void>('/generate', { deck, prompt, bpm, duration }),
    play: (deck) => post<void>('/play', { deck }),
    crossfade: (target, bars) => post<void>('/crossfade', { target, bars }),
    gain: (deck, gainDb) => post<void>('/gain', { deck, gain_db: gainDb }),
    filter: (deck, kind, frequencyHz) =>
      post<void>('/filter', { deck, kind, frequency_hz: frequencyHz }),
    record: (action) => post<void>('/record', { action }),
    feedback: (kind) => post<void>('/feedback', { kind }),
    subscribe: (onChange) => {
      if (typeof EventSource === 'undefined') return () => {}
      let source: EventSource | null = null
      try {
        source = new EventSource(`${API_BASE}/events`)
        source.onmessage = () => onChange()
        // An error here means the server is absent. Stay silent: the UI already reports
        // unavailability through snapshot(), and audio is unaffected either way.
        source.onerror = () => {}
      } catch {
        return () => {}
      }
      return () => source?.close()
    },
  }
}
