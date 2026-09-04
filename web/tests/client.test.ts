import { afterEach, describe, expect, it, vi } from 'vitest'
import { createLiveClient, TIMEOUT_MS } from '../src/adapter/client'

afterEach(() => vi.unstubAllGlobals())

describe('local operation time budgets', () => {
  it('does not confuse normal SuperCollider startup with a failed request', () => {
    expect(TIMEOUT_MS.process).toBeGreaterThan(20_000)
  })

  it('allows local Magenta generation to outlive the server command budget', () => {
    expect(TIMEOUT_MS.generation).toBeGreaterThan(600_000)
  })
})

describe('control-room adapter', () => {
  it('maps phrase scheduling and Codex turns to the local HTTP contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const client = createLiveClient()

    await client.streamSchedule(2, 0.65, 16, 8)
    await client.sendCodexTurn('inspect the stream guard')
    await client.steerCodexTurn('keep the fallback latched')

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/stream/schedule',
      expect.objectContaining({
        body: JSON.stringify({ slot: 2, weight: 0.65, phrase_bars: 16, morph_bars: 8 }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/codex/turn',
      expect.objectContaining({ body: JSON.stringify({ prompt: 'inspect the stream guard' }) }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/codex/steer',
      expect.objectContaining({ body: JSON.stringify({ prompt: 'keep the fallback latched' }) }),
    )
  })
})
