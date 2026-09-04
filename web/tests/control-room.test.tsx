import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { App } from '../src/App'

describe('control room', () => {
  it('keeps audible truth, all prompt lanes, and the local Codex desk in one view', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/?demo=true')
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Control room' }))

    expect(screen.getByRole('heading', { name: 'Continuous engine' })).toBeVisible()
    expect(screen.getByText('MRT2 on air')).toBeVisible()
    expect(screen.getAllByRole('slider', { name: /^Prompt lane \d weight$/i })).toHaveLength(6)
    expect(screen.getByRole('heading', { name: 'Codex thread' })).toBeVisible()
    expect(screen.getByText('Bridge ready')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Send new turn' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Steer active turn' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'New thread' }))
    expect(screen.getByRole('button', { name: 'Start thread' })).toBeDisabled()
    expect(screen.getByText(/replace the current session attachment/i)).toBeVisible()
  })

  it('does not erase an in-progress prompt edit when live snapshot data changes', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/?demo=true')
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Control room' }))

    const lane = screen.getByRole('textbox', { name: 'Prompt lane 1' })
    await user.clear(lane)
    await user.type(lane, 'dry broken beat, no filter sweeps')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Scenario' }), 'agent-absent')

    expect(screen.getByRole('textbox', { name: 'Prompt lane 1' })).toHaveValue(
      'dry broken beat, no filter sweeps',
    )
    expect(screen.getByRole('slider', { name: 'Prompt lane 2 weight' })).toHaveValue('0.4')
  })
})
