import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { App } from '../src/App'
import { createLiveClient } from '../src/adapter/client'
import { buildScenario } from '../src/demo/fixtures'
import { SetSteerer } from '../src/pages/SetSteerer'

describe('set steerer', () => {
  it('is the default surface and keeps manual controls backstage', async () => {
    window.history.replaceState({}, '', '/?demo=true')
    render(<App />)

    expect(await screen.findByRole('heading', { name: /modern Indian house fusion/i })).toBeVisible()
    expect(screen.getByText('THE ARC')).toBeVisible()
    expect(screen.getByLabelText('TELL THE DJ')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Hold this' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Control room' })).toHaveTextContent('Manual')
  })

  it('makes a stopped set one brief and one explicit start action', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/?demo=true&scenario=offline')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'What should the next hour feel like?' })).toBeVisible()
    expect(screen.getByLabelText('THE BRIEF')).toHaveValue(
      'Modern Indian house fusion — warm hand percussion, deep bass, modal melody, patient evolution, stable timbre',
    )
    expect(screen.getByRole('button', { name: 'START 90-MINUTE SET' })).toBeEnabled()
    await user.selectOptions(screen.getByLabelText('LENGTH'), '120')
    expect(screen.getByRole('button', { name: 'START 120-MINUTE SET' })).toBeEnabled()
    expect(screen.getByText(/Nothing starts until you press Start/i)).toBeVisible()
  })

  it('never claims on-air when the audio runtime is down', () => {
    const snapshot = buildScenario('live-safe')
    snapshot.runtime = { ok: false, running: false, pid: null, local_only: true }
    render(
      <SetSteerer snapshot={snapshot} client={createLiveClient()} demo
        onRefresh={async () => {}} announce={() => {}} />,
    )

    expect(screen.queryByText(/ON AIR · LOCAL CONDUCTOR/i)).toBeNull()
    expect(screen.getByRole('heading', { name: 'No music is playing.' })).toBeVisible()
    expect(screen.getByText(/conductor process is still waiting/i)).toBeVisible()
    expect(screen.getByRole('button', { name: /CLEAR CONDUCTOR · DO NOT START AUDIO/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /START \d+-MINUTE SET/i })).toBeNull()
  })
})
