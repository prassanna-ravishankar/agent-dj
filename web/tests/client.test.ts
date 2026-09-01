import { describe, expect, it } from 'vitest'
import { TIMEOUT_MS } from '../src/adapter/client'

describe('local operation time budgets', () => {
  it('does not confuse normal SuperCollider startup with a failed request', () => {
    expect(TIMEOUT_MS.process).toBeGreaterThan(20_000)
  })

  it('allows local Magenta generation to outlive the server command budget', () => {
    expect(TIMEOUT_MS.generation).toBeGreaterThan(600_000)
  })
})
