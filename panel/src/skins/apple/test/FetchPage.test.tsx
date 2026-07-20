import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { SourceInfo, SourcesResponse } from '@core/types'
import { FetchPage } from '../pages/FetchPage'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

type MotionElementProps<T extends HTMLElement> = HTMLAttributes<T> & {
  animate?: unknown
  initial?: unknown
  variants?: unknown
}

vi.mock('framer-motion', () => ({
  m: {
    div: ({
      children,
      animate: _animate,
      initial: _initial,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLDivElement>) => <div {...props}>{children}</div>,
    form: ({
      children,
      animate: _animate,
      initial: _initial,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLFormElement>) => <form {...props}>{children}</form>,
    article: ({
      children,
      animate: _animate,
      initial: _initial,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLElement>) => <article {...props}>{children}</article>,
  },
}))

vi.mock('../components/common/Skeleton', () => ({
  ResultsSkeleton: () => <div>loading</div>,
}))

function source(overrides: Partial<SourceInfo> = {}): SourceInfo {
  return {
    name: 'builtin',
    domain: 'web',
    category: 'fetch',
    capabilities: ['fetch'],
    description: 'Built-in fetcher',
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: true,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: ['web:fetch'],
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    runtime_available: true,
    runtime_reason: '',
    available: true,
    ...overrides,
  }
}

function sourcesResponse(): SourcesResponse {
  return {
    sources: [source()],
    categories: [],
    defaults: { 'web:fetch': ['builtin'] },
  }
}

describe('Apple FetchPage accessibility', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('exposes fetch form controls through accessible labels', async () => {
    const user = userEvent.setup()

    render(<FetchPage />)

    expect(screen.getByLabelText('fetch.urlsLabel')).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.provider')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'advancedSearch.title' }))

    expect(screen.getByLabelText(/^fetch.timeout/)).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.strategy')).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.startIndex')).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.maxLength')).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.selector')).toBeInTheDocument()
    expect(screen.getByLabelText('fetch.respectRobots')).toBeInTheDocument()
  })
})
