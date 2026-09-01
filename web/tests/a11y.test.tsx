import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GestureRow } from '../src/components/GestureRow'
import { ShortcutOverlay } from '../src/components/ShortcutOverlay'
import { Decks } from '../src/components/Decks'
import { buildScenario } from '../src/demo/fixtures'
import { selectView } from '../src/state/selectors'
import { FEEDBACK } from '../src/adapter/policy'

const NOW = Date.now()

describe('gesture row', () => {
  it('prints each gesture consequence permanently, not on hover', () => {
    render(<GestureRow onFeedback={() => {}} pendingKind={null} disabled={false} disabledReason={null} />)
    for (const f of FEEDBACK) {
      expect(screen.getByText(f.label)).toBeVisible()
      const sign = f.energyDelta >= 0 ? '+' : '−'
      expect(
        screen.getByText(`${f.bars} bars · ${sign}${Math.abs(f.energyDelta).toFixed(2)}`),
      ).toBeVisible()
    }
  })

  it('declares its keyboard shortcut on each control', () => {
    render(<GestureRow onFeedback={() => {}} pendingKind={null} disabled={false} disabledReason={null} />)
    for (const f of FEEDBACK) {
      expect(screen.getByRole('button', { name: new RegExp(f.label, 'i') }))
        .toHaveAttribute('aria-keyshortcuts', f.key)
    }
  })

  it('is operable by keyboard alone', async () => {
    const onFeedback = vi.fn()
    const user = userEvent.setup()
    render(<GestureRow onFeedback={onFeedback} pendingKind={null} disabled={false} disabledReason={null} />)
    await user.tab()
    expect(screen.getByRole('button', { name: /LOVE/i })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onFeedback).toHaveBeenCalledWith('love')
  })

  it('explains why it is disabled rather than failing silently', () => {
    render(
      <GestureRow onFeedback={() => {}} pendingKind={null} disabled
        disabledReason="Runtime is offline — feedback needs a running session." />,
    )
    expect(screen.getByText(/Runtime is offline/)).toBeVisible()
    expect(screen.getByRole('button', { name: /LOVE/i })).toBeDisabled()
  })
})

describe('decks', () => {
  it('announces the on-air deck to assistive technology', () => {
    const snap = buildScenario('live-safe', NOW)
    const v = selectView(snap, NOW)
    const { container } = render(
      <Decks decks={snap.state.decks} onAir={v.onAir} pending={v.pending}
        seamProgress={v.seamProgress} barsUntilLanding={v.barsUntilLanding}
        focused="A" onFocus={() => {}} />,
    )
    const live = container.querySelector('[aria-live="polite"]')
    expect(live?.textContent).toBe('Deck A is on air.')
  })

  it('exposes each deck with its status in the accessible name', () => {
    const snap = buildScenario('live-safe', NOW)
    const v = selectView(snap, NOW)
    render(
      <Decks decks={snap.state.decks} onAir={v.onAir} pending={v.pending}
        seamProgress={v.seamProgress} barsUntilLanding={v.barsUntilLanding}
        focused="A" onFocus={() => {}} />,
    )
    expect(screen.getByLabelText('Deck A, on air')).toBeInTheDocument()
    expect(screen.getByLabelText('Deck B, prepared')).toBeInTheDocument()
  })
})

describe('shortcut overlay', () => {
  it('is a labelled modal dialog that takes focus', () => {
    render(<ShortcutOverlay onClose={() => {}} />)
    const dialog = screen.getByRole('dialog', { name: /keyboard shortcuts/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveFocus()
  })

  it('closes on the close control', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<ShortcutOverlay onClose={onClose} />)
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
