import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { App } from '../src/App'

describe('control room', () => {
  it('puts performance first while keeping shaping and Codex one action away', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/?demo=true')
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Control room' }))

    expect(screen.getByRole('heading', { name: 'MRT2 on air' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Move through the continuous sound' })).toBeVisible()
    expect(screen.getByRole('button', { name: /^Lean into prompt 1:/i })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Shape' }))
    expect(screen.getByRole('heading', { name: 'Continuous engine' })).toBeVisible()
    expect(screen.getAllByRole('slider', { name: /^Prompt lane \d weight$/i })).toHaveLength(6)

    await user.click(screen.getByRole('button', { name: 'Codex' }))
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
    await user.click(screen.getByRole('button', { name: 'Shape' }))

    const lane = screen.getByRole('textbox', { name: 'Prompt lane 1' })
    await user.clear(lane)
    await user.type(lane, 'dry broken beat, no filter sweeps')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Scenario' }), 'agent-absent')

    expect(screen.getByRole('textbox', { name: 'Prompt lane 1' })).toHaveValue(
      'dry broken beat, no filter sweeps',
    )
    expect(screen.getByRole('slider', { name: 'Prompt lane 2 weight' })).toHaveValue('0.4')
  })

  it('states that nothing is audible and offers one launch action while stopped', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/?demo=true&scenario=offline')
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Control room' }))

    expect(screen.getByRole('heading', { name: 'Nothing — runtime stopped' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Start performance' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Shape' }))
    expect(screen.getByRole('button', { name: 'Start phrase scheduling' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Morph lane 1 now' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Start stream' })).toBeNull()
  })
})
