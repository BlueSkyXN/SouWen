import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { SourceInfo, SourcesResponse } from '@core/types'
import { VideoPage } from '../pages/VideoPage'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
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
    }: MotionDivProps) => <div {...props}>{children}</div>,
  },
}))

function videoSource(overrides: Partial<SourceInfo> = {}): SourceInfo {
  return {
    name: 'duckduckgo_videos',
    domain: 'web',
    category: 'web_general',
    capabilities: ['search_videos'],
    description: 'Video search',
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: true,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: ['web:search_videos'],
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    available: true,
    ...overrides,
  }
}

function sourcesResponse(): SourcesResponse {
  return {
    sources: [videoSource()],
    categories: [],
    defaults: { 'web:search_videos': ['duckduckgo_videos'] },
  }
}

describe('SouWen Nebula VideoPage accessibility', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('exposes video controls through accessible labels across tabs', async () => {
    const user = userEvent.setup()

    render(<VideoPage />)

    expect(screen.getByLabelText('video.region')).toBeInTheDocument()
    expect(screen.getByLabelText('video.category')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'video.search' }))
    expect(screen.getByLabelText('video.searchPlaceholder')).toBeInTheDocument()
    expect(await screen.findByLabelText('video.searchSource')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'video.bilibili' }))
    expect(screen.getByLabelText('video.bilibiliPlaceholder')).toBeInTheDocument()
    expect(screen.getByLabelText('video.bilibiliOrder')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'video.transcript' }))
    expect(screen.getByLabelText('video.videoId')).toBeInTheDocument()
    expect(screen.getByLabelText('video.language')).toBeInTheDocument()
  })
})
