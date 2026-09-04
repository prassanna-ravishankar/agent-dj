/**
 * Hand-written mirror of dj/models.py, dj/observations.py, dj/policy.py, dj/scheduler.py.
 *
 * Hand-written rather than generated so the mirror stays reviewable. tests/contract.test.ts
 * asserts the field sets below still match the Pydantic models.
 *
 * RULE: nullable stays nullable all the way to the component. Never `?? 0` a measurement —
 * absent, empty and zero are three distinct states (PRODUCT.md 13.4).
 */

export type DeckName = 'A' | 'B'

export type DeckStatus = 'stopped' | 'preparing' | 'prepared' | 'playing' | 'failed'

/** dj/models.py TransportState */
export interface TransportState {
  playing: boolean
  bpm: number
  bar: number
  beat: number
  /** ISO-8601. Retained after stop — never treat non-null as evidence of playback. */
  started_at: string | null
  sample_position: number
}

/** dj/models.py DeckState */
export interface DeckState {
  name: DeckName
  status: DeckStatus
  /** "fake" | "magenta" — free-form in Python, so kept as string. */
  source: string
  prompt: string | null
  /** Default -60 (loaded but silent), not 0. */
  gain_db: number
  /** Agent-maintained intention, clamped 0..1. NOT measured from audio. */
  energy: number | null
  audio_path: string | null
  duration_seconds: number | null
}

/** dj/models.py MasterState — every field is null in all recorded sessions. */
export interface MasterState {
  peak_dbfs: number | null
  lufs_short: number | null
  limiter_reduction_db: number
}

/** dj/models.py FutureState */
export interface FutureState {
  covered_until_bar: number
  /** 86_400 is a sentinel meaning "indefinite" — render SAFE, never a duration. */
  estimated_seconds: number
}

/** Continuous MRT2 prompt lane. Weights are normalized by the engine. */
export interface StreamPrompt {
  slot: number
  text: string
  weight: number
}

/** dj/models.py StreamState — fallback is the audible safety floor. */
export interface StreamState {
  available: boolean
  enabled: boolean
  healthy: boolean
  fallback_active: boolean
  stream_active: boolean
  warming_up: boolean
  signal_detected: boolean
  phase: string
  force_fallback: boolean
  signal_level: number | null
  mix: number
  temperature: number
  top_k: number
  prompts: StreamPrompt[]
}

/** dj/models.py CodexState — the thread belongs to this DJ session. */
export interface CodexState {
  thread_id: string | null
  turn_id: string | null
  turn_status: string
}

/** dj/observations.py Observation */
export interface Observation {
  id: string
  source: string
  kind: string
  value: unknown
  confidence: number
  timestamp: string
  metadata: Record<string, unknown>
}

/** dj/models.py DJState */
export interface DJState {
  session_id: string
  /** "development" | "live" | "stopped" — free-form in Python. */
  status: string
  transport: TransportState
  decks: Record<DeckName, DeckState>
  master: MasterState
  future: FutureState
  stream: StreamState
  codex: CodexState
  observations: Observation[]
  updated_at: string
}

/** dj/agent.py + dj/runtime.py status payload. */
export interface ProcessHealth {
  ok: boolean
  running: boolean
  pid: number | null
  local_only: boolean
}

/** Project-local Codex bridge health, included in every snapshot. */
export interface CodexBridgeHealth {
  ok: boolean
  running: boolean
  available: boolean
  pid: number | null
  transport_local_only: boolean
  inference_may_require_network: boolean
}

/** App-server thread summaries are intentionally tolerant across Codex versions. */
export interface CodexThreadSummary {
  id: string
  preview?: string
  name?: string
  model?: string
  status?: string
  createdAt?: number | string
  updatedAt?: number | string
  [key: string]: unknown
}

export interface CodexThreadsResponse {
  data?: CodexThreadSummary[]
  threads?: CodexThreadSummary[]
  nextCursor?: string | null
  [key: string]: unknown
}

export interface CodexModelSummary {
  id: string
  displayName?: string
  isDefault?: boolean
  [key: string]: unknown
}

export interface CodexModelsResponse {
  data?: CodexModelSummary[]
  models?: CodexModelSummary[]
  [key: string]: unknown
}

export interface CodexThreadResponse {
  thread?: Record<string, unknown>
  turn?: Record<string, unknown>
  [key: string]: unknown
}

/** dj/policy.py Decision */
export interface Decision {
  observation_id: string
  goal: string
  evidence: string[]
  target_deck: DeckName
  prompt: string
  transition_bars: number
  energy_delta: number
}

/** dj/scheduler.py ScheduleStore.append */
export interface ScheduleItem {
  id: string
  created_at: string
  status: string
  action: string
  target: string
  at_bar: number
  parameters: Record<string, unknown>
}

/** dj/events.py — ts + type + open payload. */
export interface EventRecord {
  ts: string
  type: string
  [key: string]: unknown
}

/** dj/observations.py FeedbackKind — exact CLI values. */
export const FEEDBACK_KINDS = [
  'love',
  'dislike',
  'more-energy',
  'less-energy',
  'boring',
  'weird',
] as const

export type FeedbackKind = (typeof FEEDBACK_KINDS)[number]

/** Implemented filters only. Delay/reverb/EQ are specified but not built. */
export const FILTER_KINDS = ['lowpass', 'highpass'] as const
export type FilterKind = (typeof FILTER_KINDS)[number]

/** dj/doctor.py inspect_environment(), narrowed to what the surface reads. */
export interface DoctorReport {
  ok: boolean
  platform: { os: string; release: string; arch: string }
  python: { version: string; executable: string; supported: boolean }
  uv: { available: boolean; path: string | null }
  supercollider: {
    sclang: string | null
    scsynth: string | null
    installed: boolean
    version: string | null
  }
  magenta: {
    python: boolean
    cli: string | null
    models_dir: string
    small_model: boolean
    live_backend: string | null
  }
  essentia: boolean
  audio: { ffmpeg: string | null; ffprobe: string | null; sample_rate: number }
  storage: { sessions_dir: string; writable: boolean; free_bytes: number }
  local_only: boolean
}

/** Everything the surface needs for one render pass. */
export interface Snapshot {
  state: DJState
  runtime: ProcessHealth
  agent: ProcessHealth
  codex_bridge: CodexBridgeHealth
  events: EventRecord[]
  decisions: Decision[]
  schedules: ScheduleItem[]
  /** True when this snapshot came from fixtures rather than a live runtime. */
  demo: boolean
}

export type AdapterErrorCode =
  | 'unavailable'
  | 'not_implemented'
  | 'refused'
  | 'invalid'
  | 'transport'

export interface AdapterError {
  code: AdapterErrorCode
  message: string
  detail?: string
}

export type Result<T> = { ok: true; value: T } | { ok: false; error: AdapterError }

export const ok = <T,>(value: T): Result<T> => ({ ok: true, value })
export const err = <T,>(error: AdapterError): Result<T> => ({ ok: false, error })
