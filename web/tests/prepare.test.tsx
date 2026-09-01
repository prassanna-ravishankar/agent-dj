import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Prepare } from '../src/pages/Prepare'
import { buildScenario } from '../src/demo/fixtures'

describe('long-running command state', () => {
  it('keeps startup visibly pending and prevents a duplicate start', () => {
    render(
      <Prepare
        snapshot={buildScenario('offline')}
        demo={false}
        pendingCommand="Runtime start"
        onGenerate={vi.fn()}
        onRuntime={vi.fn()}
        onAgent={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Starting runtime…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Start agent' })).toBeDisabled()
  })
})
