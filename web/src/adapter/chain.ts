/**
 * Groups the causal chain into ONE entity per observation that accrues stages
 * (fused from probe C): Observation -> Decision -> Generation -> Schedule.
 *
 * Everything here is read from artifacts the system already writes:
 *   observations.jsonl, decisions.jsonl, schedules.jsonl, events.jsonl
 * joined on observation_id. Nothing is inferred beyond that join.
 */

import type { Decision, EventRecord, Observation, ScheduleItem } from './types'

export type StageName = 'observation' | 'decision' | 'generation' | 'schedule'

export const STAGE_ORDER: readonly StageName[] = [
  'observation',
  'decision',
  'generation',
  'schedule',
] as const

export type StageStatus = 'complete' | 'active' | 'failed' | 'pending'

export interface Stage {
  name: StageName
  status: StageStatus
  ts: string | null
  /** Short human line drawn from the artifact, never invented. */
  detail: string | null
}

export interface ChainEntity {
  observationId: string
  observation: Observation | null
  decision: Decision | null
  schedule: ScheduleItem | null
  stages: Stage[]
  /** Bar this entity's transition is scheduled to land on, if scheduled. */
  atBar: number | null
  /** True once the schedule has executed. */
  executed: boolean
  /** True if generation failed for this entity. */
  failed: boolean
  ts: string
}

function eventObservationId(event: EventRecord): string | null {
  const id = event['observation_id']
  return typeof id === 'string' ? id : null
}

/**
 * Build one entity per observation, newest first.
 *
 * Events without an observation_id (manual deck loads, runtime lifecycle, parameter changes)
 * are deliberately excluded — they are not part of a causal chain and belong in the event
 * stream instead.
 */
export function buildChain(
  observations: Observation[],
  decisions: Decision[],
  schedules: ScheduleItem[],
  events: EventRecord[],
): ChainEntity[] {
  const byObservation = new Map<string, EventRecord[]>()
  for (const event of events) {
    const id = eventObservationId(event)
    if (!id) continue
    const bucket = byObservation.get(id)
    if (bucket) bucket.push(event)
    else byObservation.set(id, [event])
  }

  const decisionFor = new Map(decisions.map((d) => [d.observation_id, d]))
  const scheduleFor = new Map<string, ScheduleItem>()
  for (const item of schedules) {
    const id = item.parameters['observation_id']
    if (typeof id === 'string') scheduleFor.set(id, item)
  }

  const ids = new Set<string>([
    ...observations.map((o) => o.id),
    ...decisions.map((d) => d.observation_id),
    ...byObservation.keys(),
  ])

  const entities: ChainEntity[] = []

  for (const id of ids) {
    const observation = observations.find((o) => o.id === id) ?? null
    const decision = decisionFor.get(id) ?? null
    const schedule = scheduleFor.get(id) ?? null
    const own = byObservation.get(id) ?? []

    const at = (type: string): EventRecord | null => own.find((e) => e.type === type) ?? null

    const received = at('observation_received')
    const decided = at('agent_decision')
    const genRequested = at('generation_requested')
    const genReady = at('generation_ready')
    const genFailed = at('generation_failed')
    const scheduled = at('transition_scheduled')
    const executed = at('schedule_executed')
    const started = at('transition_started')

    const failed = genFailed !== null

    const stages: Stage[] = [
      {
        name: 'observation',
        status: observation || received ? 'complete' : 'pending',
        ts: observation?.timestamp ?? (received?.ts as string | undefined) ?? null,
        detail: observation ? `${observation.source} · ${observation.kind}` : null,
      },
      {
        name: 'decision',
        status: decision || decided ? 'complete' : 'pending',
        ts: (decided?.ts as string | undefined) ?? null,
        detail: decision?.goal ?? null,
      },
      {
        name: 'generation',
        status: failed
          ? 'failed'
          : genReady
            ? 'complete'
            : genRequested
              ? 'active'
              : 'pending',
        ts:
          (genFailed?.ts as string | undefined) ??
          (genReady?.ts as string | undefined) ??
          (genRequested?.ts as string | undefined) ??
          null,
        detail: failed
          ? typeof genFailed?.['error'] === 'string'
            ? (genFailed['error'] as string)
            : 'generation failed'
          : decision
            ? `deck ${decision.target_deck}`
            : null,
      },
      {
        name: 'schedule',
        status: executed || started ? 'complete' : schedule || scheduled ? 'active' : 'pending',
        ts:
          (started?.ts as string | undefined) ??
          (executed?.ts as string | undefined) ??
          (scheduled?.ts as string | undefined) ??
          null,
        detail: schedule
          ? `${schedule.action} → ${schedule.target} at bar ${schedule.at_bar}`
          : null,
      },
    ]

    const ts =
      observation?.timestamp ??
      (received?.ts as string | undefined) ??
      (decided?.ts as string | undefined) ??
      new Date(0).toISOString()

    entities.push({
      observationId: id,
      observation,
      decision,
      schedule,
      stages,
      atBar: schedule?.at_bar ?? null,
      executed: executed !== null || started !== null,
      failed,
      ts,
    })
  }

  return entities.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))
}

/** Entities still travelling toward their landing bar — the ghost ticks on the horizon. */
export function inFlight(entities: ChainEntity[]): ChainEntity[] {
  return entities.filter((e) => !e.executed && !e.failed && e.atBar !== null)
}

export function stageLabel(name: StageName): string {
  return name.toUpperCase()
}
