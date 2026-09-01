/**
 * DEMO FIXTURES — visibly and permanently marked DEMO DATA wherever rendered.
 *
 * Derived from real artifacts under sessions/: real prompts, real goal/evidence strings from
 * decisions.jsonl, real event shapes and types from events.jsonl. Timestamps are shifted to
 * "now" so the clock derivation exercises properly. No capability that the system does not
 * have appears in any fixture.
 */

import type {
  Decision,
  DeckName,
  DJState,
  DoctorReport,
  EventRecord,
  Observation,
  ProcessHealth,
  ScheduleItem,
  Snapshot,
} from '../adapter/types'
import { SAFE_SENTINEL_SECONDS } from '../adapter/coverage'
import { secondsPerBar } from '../adapter/clock'

export type ScenarioId =
  | 'live-safe'
  | 'coverage-warning'
  | 'coverage-critical'
  | 'agent-absent'
  | 'generation-failed'
  | 'clock-uncertain'
  | 'recording'
  | 'offline'
  | 'empty'

export interface Scenario {
  id: ScenarioId
  label: string
  /** What a reviewer should look for. */
  note: string
}

export const SCENARIOS: readonly Scenario[] = [
  { id: 'live-safe', label: 'Live · safe', note: 'Deck A on air, coverage sentinel renders SAFE, one intent in flight.' },
  { id: 'coverage-warning', label: 'Coverage warning', note: 'Under 60s of covered future; falloff pulls toward now.' },
  { id: 'coverage-critical', label: 'Coverage critical', note: 'Under 30s; agent refuses creative change without a safe buffer.' },
  { id: 'agent-absent', label: 'Agent absent', note: 'Survivable and calm — music continues, no new decisions.' },
  { id: 'generation-failed', label: 'Generation failed', note: 'Deck B failed; deck A continues; transition cancelled.' },
  { id: 'clock-uncertain', label: 'Clock uncertain', note: 'started_at later than updated_at — derived bar withdrawn.' },
  { id: 'recording', label: 'Recording', note: 'Persistent red edge along the full top of the viewport.' },
  { id: 'offline', label: 'Runtime offline', note: 'No audio from this system; horizon replaced by a plain statement.' },
  { id: 'empty', label: 'Fresh session', note: 'Nothing prepared yet — empty states, not zeros.' },
]

const HOUSE_A = 'warm groovy house, around 124 BPM'
const HOUSE_B =
  'groovy instrumental house, more driving, denser percussion, stronger bass movement, instrumental'

const iso = (ms: number) => new Date(ms).toISOString()

function baseState(now: number, bpm = 124): DJState {
  // Place the transport a musically plausible distance into the set.
  const startedMs = now - 184 * secondsPerBar(bpm) * 1000
  return {
    session_id: 'demo-warehouse-set',
    status: 'live',
    transport: {
      playing: true,
      bpm,
      bar: 0,
      beat: 0,
      started_at: iso(startedMs),
      sample_position: 0,
    },
    decks: {
      A: {
        name: 'A',
        status: 'playing',
        source: 'magenta',
        prompt: HOUSE_A,
        gain_db: 0,
        energy: 0.55,
        audio_path: 'sessions/demo-warehouse-set/generated/A-221408.wav',
        duration_seconds: 16,
      },
      B: {
        name: 'B',
        status: 'prepared',
        source: 'magenta',
        prompt: HOUSE_B,
        gain_db: -60,
        energy: 0.75,
        audio_path: 'sessions/demo-warehouse-set/generated/reaction-B-220329.wav',
        duration_seconds: 16,
      },
    },
    master: { peak_dbfs: null, lufs_short: null, limiter_reduction_db: 0 },
    future: { covered_until_bar: 192, estimated_seconds: SAFE_SENTINEL_SECONDS },
    observations: [],
    updated_at: iso(now - 400),
  }
}

const health = (running: boolean, pid: number | null): ProcessHealth => ({
  ok: running,
  running,
  pid: running ? pid : null,
  local_only: true,
})

function observation(id: string, kind: string, tsMs: number): Observation {
  return {
    id,
    source: 'human',
    kind,
    value: true,
    confidence: 1,
    timestamp: iso(tsMs),
    metadata: {},
  }
}

function decision(observationId: string, target: DeckName): Decision {
  return {
    observation_id: observationId,
    goal: 'increase energy through density and drive',
    evidence: ['human:more-energy', 'confidence=1.00', 'current_deck=A'],
    target_deck: target,
    prompt: HOUSE_B,
    transition_bars: 4,
    energy_delta: 0.2,
  }
}

function schedule(observationId: string, atBar: number, tsMs: number): ScheduleItem {
  return {
    id: `schedule-${(tsMs / 1000).toFixed(6)}`,
    created_at: iso(tsMs),
    status: 'pending',
    action: 'crossfade',
    target: 'B',
    at_bar: atBar,
    parameters: { bars: 4, observation_id: observationId },
  }
}

function chainEvents(observationId: string, tsMs: number, atBar: number): EventRecord[] {
  return [
    { ts: iso(tsMs), type: 'observation_received', observation_id: observationId },
    {
      ts: iso(tsMs + 120),
      type: 'agent_decision',
      observation_id: observationId,
      goal: 'increase energy through density and drive',
      evidence: ['human:more-energy', 'confidence=1.00', 'current_deck=A'],
      actions: ['generate deck B', 'schedule phrase-aligned transition'],
    },
    {
      ts: iso(tsMs + 200),
      type: 'generation_requested',
      observation_id: observationId,
      deck: 'B',
      prompt: HOUSE_B,
      source: 'agent_decision',
    },
    {
      ts: iso(tsMs + 4200),
      type: 'generation_ready',
      observation_id: observationId,
      deck: 'B',
      backend: 'magenta-live-mlx',
      realtime_factor: 0.41,
    },
    {
      ts: iso(tsMs + 4300),
      type: 'transition_scheduled',
      observation_id: observationId,
      action: 'crossfade',
      target: 'B',
      at_bar: atBar,
    },
  ]
}

const lifecycleEvents = (now: number): EventRecord[] => [
  { ts: iso(now - 3_600_000), type: 'session_created', session_id: 'demo-warehouse-set' },
  {
    ts: iso(now - 3_590_000),
    type: 'set_intent',
    planned_duration_minutes: 90,
    planned_duration_seconds: 5400,
  },
  {
    ts: iso(now - 3_580_000),
    type: 'runtime_started',
    pid: 48211,
    test_mode: false,
    backend: 'supercollider',
  },
  { ts: iso(now - 3_570_000), type: 'deck_started', deck: 'A' },
]

export const DEMO_DOCTOR: DoctorReport = {
  ok: true,
  platform: { os: 'Darwin', release: '15.2', arch: 'arm64' },
  python: { version: '3.12.8', executable: '/usr/bin/python3.12', supported: true },
  uv: { available: true, path: '/opt/homebrew/bin/uv' },
  supercollider: {
    sclang: '/Applications/SuperCollider.app/Contents/MacOS/sclang',
    scsynth: '/Applications/SuperCollider.app/Contents/MacOS/scsynth',
    installed: true,
    version: '3.13.0',
  },
  magenta: {
    python: true,
    cli: null,
    models_dir: 'models',
    small_model: true,
    live_backend: 'mlx',
  },
  essentia: false,
  audio: { ffmpeg: '/opt/homebrew/bin/ffmpeg', ffprobe: '/opt/homebrew/bin/ffprobe', sample_rate: 48_000 },
  storage: { sessions_dir: 'sessions', writable: true, free_bytes: 412_000_000_000 },
  local_only: true,
}

export function buildScenario(id: ScenarioId, now: number = Date.now()): Snapshot {
  const state = baseState(now)
  let runtime = health(true, 48211)
  let agent = health(true, 48219)
  const events: EventRecord[] = lifecycleEvents(now)
  const decisions: Decision[] = []
  const schedules: ScheduleItem[] = []
  const observations: Observation[] = []

  // An intent already in flight, landing on the next phrase boundary.
  const obsMs = now - 9_000
  const landingBar = 188
  const inFlightObs = observation('obs-426213acd7d54ff3a7b7b5b3f3ee2e14', 'more-energy', obsMs)

  const addInFlight = () => {
    observations.push(inFlightObs)
    decisions.push(decision(inFlightObs.id, 'B'))
    schedules.push(schedule(inFlightObs.id, landingBar, obsMs + 4300))
    events.push(...chainEvents(inFlightObs.id, obsMs, landingBar))
  }

  // A completed entity, so the chain shows history as well as pending work.
  const doneMs = now - 240_000
  const doneObs = observation('obs-8fa1c2d34e5b46789a0bcdef12345678', 'love', doneMs)
  const addCompleted = () => {
    observations.push(doneObs)
    decisions.push({
      observation_id: doneObs.id,
      goal: 'reinforce what is working without a sharp change',
      evidence: ['human:love', 'confidence=1.00', 'current_deck=B'],
      target_deck: 'A',
      prompt: `${HOUSE_A}, preserve the groove, subtle evolution, patient arrangement`,
      transition_bars: 8,
      energy_delta: 0.05,
    })
    schedules.push({
      id: `schedule-${((doneMs + 5000) / 1000).toFixed(6)}`,
      created_at: iso(doneMs + 5000),
      status: 'pending',
      action: 'crossfade',
      target: 'A',
      at_bar: 168,
      parameters: { bars: 8, observation_id: doneObs.id },
    })
    events.push(
      { ts: iso(doneMs), type: 'observation_received', observation_id: doneObs.id },
      {
        ts: iso(doneMs + 100),
        type: 'agent_decision',
        observation_id: doneObs.id,
        goal: 'reinforce what is working without a sharp change',
      },
      { ts: iso(doneMs + 200), type: 'generation_requested', observation_id: doneObs.id, deck: 'A' },
      {
        ts: iso(doneMs + 5000),
        type: 'generation_ready',
        observation_id: doneObs.id,
        deck: 'A',
        backend: 'magenta-live-mlx',
        realtime_factor: 0.38,
      },
      {
        ts: iso(doneMs + 5100),
        type: 'transition_scheduled',
        observation_id: doneObs.id,
        at_bar: 168,
      },
      {
        ts: iso(doneMs + 30_000),
        type: 'transition_started',
        observation_id: doneObs.id,
        to: 'A',
        duration_bars: 8,
        observation_driven: true,
      },
      {
        ts: iso(doneMs + 30_100),
        type: 'schedule_executed',
        observation_id: doneObs.id,
        action: 'crossfade',
      },
    )
  }

  switch (id) {
    case 'live-safe':
      addCompleted()
      addInFlight()
      break

    case 'coverage-warning':
      addCompleted()
      addInFlight()
      state.future = { covered_until_bar: 186, estimated_seconds: 47 }
      events.push({
        ts: iso(now - 2_000),
        type: 'warning',
        kind: 'future_coverage_warning',
        estimated_seconds: 47,
      })
      break

    case 'coverage-critical':
      addCompleted()
      state.future = { covered_until_bar: 185, estimated_seconds: 18 }
      state.decks.B.status = 'preparing'
      events.push({
        ts: iso(now - 1_500),
        type: 'warning',
        kind: 'future_coverage_critical',
        estimated_seconds: 18,
      })
      break

    case 'agent-absent':
      addCompleted()
      agent = health(false, null)
      events.push({
        ts: iso(now - 60_000),
        type: 'error',
        subsystem: 'agent',
        error: 'agent process exited',
      })
      break

    case 'generation-failed': {
      addCompleted()
      observations.push(inFlightObs)
      decisions.push(decision(inFlightObs.id, 'B'))
      state.decks.B.status = 'failed'
      state.decks.B.audio_path = null
      state.decks.B.energy = null
      events.push(
        { ts: iso(obsMs), type: 'observation_received', observation_id: inFlightObs.id },
        {
          ts: iso(obsMs + 120),
          type: 'agent_decision',
          observation_id: inFlightObs.id,
          goal: 'increase energy through density and drive',
        },
        {
          ts: iso(obsMs + 200),
          type: 'generation_requested',
          observation_id: inFlightObs.id,
          deck: 'B',
        },
        {
          ts: iso(obsMs + 3_000),
          type: 'generation_failed',
          observation_id: inFlightObs.id,
          deck: 'B',
          error: 'MLX inference failed: model state unavailable',
        },
      )
      break
    }

    case 'clock-uncertain':
      addCompleted()
      addInFlight()
      // Defect 1, reproduced exactly: started_at later than updated_at.
      state.updated_at = iso(now - 90_000)
      state.transport.started_at = iso(now - 1_000)
      break

    case 'recording':
      addCompleted()
      addInFlight()
      events.push({
        ts: iso(now - 600_000),
        type: 'recording_started',
        path: 'sessions/demo-warehouse-set/renders/master.wav',
      })
      break

    case 'offline':
      runtime = health(false, null)
      agent = health(false, null)
      state.status = 'stopped'
      state.transport.playing = false
      state.decks.A.status = 'prepared'
      state.decks.B.status = 'prepared'
      state.future = { covered_until_bar: 0, estimated_seconds: 0 }
      events.push({ ts: iso(now - 30_000), type: 'runtime_stopped' })
      break

    case 'empty':
      runtime = health(false, null)
      agent = health(false, null)
      state.session_id = 'demo-fresh-session'
      state.status = 'development'
      state.transport = {
        playing: false,
        bpm: 124,
        bar: 0,
        beat: 0,
        started_at: null,
        sample_position: 0,
      }
      state.decks.A = {
        name: 'A',
        status: 'stopped',
        source: 'fake',
        prompt: null,
        gain_db: -60,
        energy: null,
        audio_path: null,
        duration_seconds: null,
      }
      state.decks.B = { ...state.decks.A, name: 'B' }
      state.future = { covered_until_bar: 0, estimated_seconds: 0 }
      events.length = 0
      events.push({
        ts: iso(now - 5_000),
        type: 'session_created',
        session_id: 'demo-fresh-session',
      })
      break
  }

  state.observations = observations
  events.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))

  return { state, runtime, agent, events, decisions, schedules, demo: true }
}

export function isRecording(events: EventRecord[]): boolean {
  let recording = false
  for (const event of events) {
    if (event.type === 'recording_started') recording = true
    else if (event.type === 'recording_stopped') recording = false
  }
  return recording
}
