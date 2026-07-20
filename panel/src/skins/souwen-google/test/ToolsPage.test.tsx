import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useAuthStore } from '@core/stores/authStore'
import { useNotificationStore } from '@core/stores/notificationStore'
import { ToolsPage } from '../pages/ToolsPage'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
  animate?: unknown
  initial?: unknown
  transition?: unknown
}

vi.mock('framer-motion', () => ({
  m: {
    div: ({
      children,
      animate: _animate,
      initial: _initial,
      transition: _transition,
      ...props
    }: MotionDivProps) => <div {...props}>{children}</div>,
  },
}))

describe('SouWen Google ToolsPage accessibility', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })
    useAuthStore.setState({ role: 'admin', features: { wayback_save: true } })
    vi.spyOn(api, 'waybackCDX').mockResolvedValue({
      url: 'https://example.com',
      snapshots: [],
      total: 0,
    })
    vi.spyOn(api, 'waybackCheck').mockResolvedValue({
      url: 'https://example.com',
      available: false,
      snapshot_url: null,
      timestamp: null,
      status: null,
    })
    vi.spyOn(api, 'waybackSave').mockResolvedValue({
      url: 'https://example.com',
      success: true,
      snapshot_url: 'https://web.archive.org/web/20260101000000/https://example.com',
      timestamp: '20260101000000',
      error: null,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
    useAuthStore.setState({ role: 'guest', features: {} })
  })

  it('exposes Wayback tool tabs and form controls through accessible names', async () => {
    const user = userEvent.setup()

    render(<ToolsPage />)

    expect(screen.getByRole('tablist', { name: 'tools.title' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'tools.cdx' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByLabelText('tools.url')).toBeInTheDocument()
    expect(screen.getByLabelText('tools.dateFrom')).toBeInTheDocument()
    expect(screen.getByLabelText('tools.dateTo')).toBeInTheDocument()
    expect(screen.getByLabelText('tools.limit')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'tools.check' }))
    expect(screen.getByRole('tab', { name: 'tools.check' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByLabelText('tools.url')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'tools.save' }))
    expect(screen.getByRole('tab', { name: 'tools.save' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByLabelText('tools.url')).toBeInTheDocument()
  })
})
