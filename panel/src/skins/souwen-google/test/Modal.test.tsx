import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
} from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from '../components/common/Modal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
  animate?: unknown
  exit?: unknown
  initial?: unknown
  transition?: unknown
}

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: forwardRef<HTMLDivElement, MotionDivProps>(
      (
        {
          children,
          animate: _animate,
          exit: _exit,
          initial: _initial,
          transition: _transition,
          ...props
        },
        ref,
      ) => <div ref={ref} {...props}>{children}</div>,
    ),
  },
}))

describe('SouWen Google Modal accessibility', () => {
  it('exposes a named dialog and focuses it when opened', () => {
    render(
      <Modal open title="Disable source" onClose={vi.fn()}>
        Confirm disable
      </Modal>,
    )

    const dialog = screen.getByRole('dialog', { name: 'Disable source' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveFocus()
  })

  it('supports Escape and close button dismissal', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <Modal open title="Disable source" onClose={onClose}>
        Confirm disable
      </Modal>,
    )

    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'common.close' }))

    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
