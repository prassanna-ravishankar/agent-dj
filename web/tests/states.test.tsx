import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { Horizon } from '../src/components/Horizon'
import { Decks } from '../src/components/Decks'
import { SegmentReadout } from '../src/components/SegmentReadout'
import { Chain } from '../src/components/Chain'
import { buildScenario, SCENARIOS } from '../src/demo/fixtures'
import { selectView } from '../src/state/selectors'

const NOW = Date.now()

function view(id: Parameters<typeof buildScenario>[0]) {
  const snap = buildScenario(id, NOW)
  return { snap, v: selectView(snap, NOW) }
}

describe('ghost segments — absent is not zero', () => {
  it('renders unavailable rather than a numeral when value is null', () => {
    render(<SegmentReadout value={null} cells={4} label="Peak" unavailableText="peak metering unavailable" />)
    const el = screen.getByRole('img')
    expect(el).toHaveAccessibleName('Peak: peak metering unavailable')
    expect(el.textContent).not.toMatch(/[0-9]/)
    expect(el.closest('[data-value]')).toHaveAttribute('data-value', 'unavailable')
  })

  it('marks a present value distinctly from an absent one', () => {
    const { container } = render(<SegmentReadout value={0} cells={2} label="Gain" decimals={0} />)
    expect(container.querySelector('[data-value]')).toHaveAttribute('data-value', 'present')
  })

  it('zero renders as zero, not as unavailable', () => {
    render(<SegmentReadout value={0} cells={2} label="Gain" unit="dB" decimals={0} />)
    expect(screen.getByRole('img')).toHaveAccessibleName('Gain: 0 dB')
  })
})

describe('coverage sentinel', () => {
  it('renders SAFE and never a duration', () => {
    const { v, snap } = view('live-safe')
    render(<Horizon clock={v.clock} coverage={v.coverage} inFlight={[]} runtimeRunning={snap.runtime.running} />)
    expect(screen.getByText('SAFE')).toBeInTheDocument()
    expect(screen.queryByText(/86400|86,400|24 h/i)).toBeNull()
  })

  it('names critical coverage explicitly', () => {
    const { v, snap } = view('coverage-critical')
    render(<Horizon clock={v.clock} coverage={v.coverage} inFlight={[]} runtimeRunning={snap.runtime.running} />)
    expect(screen.getByLabelText('Coverage horizon')).toHaveAttribute('data-state', 'coverage-critical')
    expect(screen.getByText(/CRITICAL/)).toBeInTheDocument()
  })
})

describe('clock uncertain', () => {
  it('withdraws the bar and explains why, without calling it an error', () => {
    const { v, snap } = view('clock-uncertain')
    render(<Horizon clock={v.clock} coverage={v.coverage} inFlight={[]} runtimeRunning={snap.runtime.running} />)
    expect(screen.getByLabelText('Coverage horizon')).toHaveAttribute('data-state', 'clock-uncertain')
    expect(screen.getByRole('img', { name: /bar position unavailable/i })).toBeInTheDocument()
    expect(screen.getByText(/Music is unaffected/)).toBeInTheDocument()
  })
})

describe('critical states carry data-state and a non-colour signal', () => {
  it('every scenario renders its state attribute', () => {
    for (const scenario of SCENARIOS) {
      const { v, snap } = view(scenario.id)
      const { container, unmount } = render(
        <Horizon clock={v.clock} coverage={v.coverage} inFlight={[]} runtimeRunning={snap.runtime.running} />,
      )
      expect(container.querySelector('[data-state]')).not.toBeNull()
      unmount()
    }
  })

  it('offline replaces the horizon with a plain statement', () => {
    const { v, snap } = view('offline')
    render(<Horizon clock={v.clock} coverage={v.coverage} inFlight={[]} runtimeRunning={snap.runtime.running} />)
    expect(screen.getByLabelText('Coverage horizon')).toHaveAttribute('data-state', 'offline')
    expect(screen.getByText('Runtime offline')).toBeInTheDocument()
  })

  it('a failed deck says the other deck continues', () => {
    const { v, snap } = view('generation-failed')
    render(
      <Decks decks={snap.state.decks} onAir={v.onAir} pending={v.pending}
        seamProgress={v.seamProgress} barsUntilLanding={v.barsUntilLanding}
        focused="A" onFocus={() => {}} />,
    )
    const deckB = screen.getByLabelText(/Deck B/)
    expect(deckB).toHaveAttribute('data-state', 'generation-failed')
    expect(within(deckB).getByText(/the other deck continues/)).toBeInTheDocument()
  })
})

describe('energy is intent, never measurement', () => {
  it('labels energy as intent', () => {
    const { v, snap } = view('live-safe')
    render(
      <Decks decks={snap.state.decks} onAir={v.onAir} pending={v.pending}
        seamProgress={v.seamProgress} barsUntilLanding={v.barsUntilLanding}
        focused="A" onFocus={() => {}} />,
    )
    expect(screen.getAllByText(/Energy \(intent\)/i).length).toBeGreaterThan(0)
  })
})

describe('causal chain', () => {
  it('groups one observation into four accruing stages', () => {
    const { v } = view('live-safe')
    render(<Chain entities={v.chain} />)
    for (const stage of ['observation', 'decision', 'generation', 'schedule']) {
      expect(screen.getAllByText(stage).length).toBeGreaterThan(0)
    }
  })

  it('quotes the policy goal verbatim', () => {
    const { v } = view('live-safe')
    render(<Chain entities={v.chain} />)
    expect(screen.getByText('increase energy through density and drive')).toBeInTheDocument()
  })

  it('empty chain explains itself without inventing capability', () => {
    render(<Chain entities={[]} />)
    expect(screen.getByText(/No observations yet/)).toBeInTheDocument()
  })
})
