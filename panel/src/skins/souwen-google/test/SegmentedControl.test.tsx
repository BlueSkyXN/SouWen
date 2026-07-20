import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { SegmentedControl } from '../components/common/SegmentedControl'

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
  layout?: boolean
  transition?: unknown
}

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: ({ children, layout: _layout, transition: _transition, ...props }: MotionDivProps) => (
      <div {...props}>{children}</div>
    ),
  },
}))

const options = [
  { value: 'paper', label: 'Paper' },
  { value: 'web', label: 'Web' },
] as const

describe('SouWen Google SegmentedControl accessibility', () => {
  it('uses an explicit accessible name for the tablist and reports selection', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <SegmentedControl
        ariaLabel="Search domain"
        options={[...options]}
        value="paper"
        onChange={onChange}
      />,
    )

    expect(screen.getByRole('tablist', { name: 'Search domain' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Paper' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Web' })).toHaveAttribute('aria-selected', 'false')

    await user.click(screen.getByRole('tab', { name: 'Web' }))

    expect(onChange).toHaveBeenCalledWith('web')
  })

  it('falls back to option labels when no accessible name is provided', () => {
    render(<SegmentedControl options={[...options]} value="web" onChange={vi.fn()} />)

    expect(screen.getByRole('tablist', { name: 'Paper / Web' })).toBeInTheDocument()
  })
})
