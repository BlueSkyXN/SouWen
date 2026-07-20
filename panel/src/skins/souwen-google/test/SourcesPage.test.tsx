import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes, ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useAuthStore } from '@core/stores/authStore'
import { useNotificationStore } from '@core/stores/notificationStore'
import type {
  DoctorResponse,
  DoctorSource,
  SourceChannelConfig,
  SourceInfo,
  SourcesResponse,
  WarpStatus,
} from '@core/types'
import { SourcesPage } from '../pages/SourcesPage'

const { translate } = vi.hoisted(() => ({
  translate: (key: string, options?: unknown) => {
    const translations: Record<string, string> = {
      'common.save': 'save',
      'sourceConfig.proxyCustomPlaceholder': 'example {{example}}',
      'sources.requiresUpgrade': 'requires upgrade',
      'sources.requiresUpgradeToEdition': 'requires {{edition}}',
    }
    const defaultValue = (
      options
      && typeof options === 'object'
      && 'defaultValue' in options
      && typeof options.defaultValue === 'string'
    ) ? options.defaultValue : undefined
    const value = translations[key] ?? defaultValue ?? key
    if (typeof options === 'string') return options
    if (
      options
      && typeof options === 'object'
      && 'example' in options
      && typeof options.example === 'string'
    ) {
      return value.replace('{{example}}', options.example)
    }
    if (
      options
      && typeof options === 'object'
      && 'edition' in options
      && typeof options.edition === 'string'
    ) {
      return value.replace('{{edition}}', options.edition)
    }
    return value
  },
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: translate,
  }),
}))

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
  animate?: unknown
  exit?: unknown
  initial?: unknown
  transition?: unknown
  variants?: unknown
}

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: ({
      children,
      animate: _animate,
      exit: _exit,
      initial: _initial,
      transition: _transition,
      variants: _variants,
      ...props
    }: MotionDivProps) => <div {...props}>{children}</div>,
  },
}))

const TEST_SOURCE_NAME = 'custom_proxy_source'

function doctorSource(overrides: Partial<DoctorSource> = {}): DoctorSource {
  return {
    name: TEST_SOURCE_NAME,
    category: 'web_general',
    status: 'ok',
    integration_type: 'scraper',
    required_key: null,
    key_requirement: 'none',
    auth_requirement: 'none',
    credential_fields: [],
    optional_credential_effect: null,
    risk_level: 'low',
    risk_reasons: [],
    distribution: 'core',
    package_extra: null,
    stability: 'stable',
    usage_note: null,
    min_edition: 'basic',
    edition: 'basic',
    edition_available: true,
    edition_reason: '',
    runtime_available: true,
    runtime_reason: '',
    credentials_satisfied: true,
    config_available: true,
    config_reason: '',
    available: true,
    message: 'Custom proxy capable source',
    enabled: true,
    ...overrides,
  }
}

function doctorResponse(sources: DoctorSource[]): DoctorResponse {
  return {
    total: sources.length,
    ok: sources.length,
    available: sources.length,
    degraded: 0,
    degraded_total: 0,
    failed: 0,
    limited: 0,
    warning: 0,
    missing_key: 0,
    unavailable: 0,
    disabled: 0,
    status_counts: { ok: sources.length },
    edition: 'basic',
    sources,
  }
}

function sourceInfo(overrides: Partial<SourceInfo> = {}): SourceInfo {
  return {
    name: TEST_SOURCE_NAME,
    domain: 'web',
    category: 'web_general',
    capabilities: ['search'],
    description: 'Custom proxy capable source',
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: true,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: [],
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    available: true,
    ...overrides,
  }
}

function sourcesResponse(sources: SourceInfo[] = [sourceInfo()]): SourcesResponse {
  return { sources, categories: [], defaults: {} }
}

function sourceConfig(overrides: Partial<SourceChannelConfig> = {}): SourceChannelConfig {
  return {
    enabled: true,
    proxy: 'inherit',
    http_backend: 'auto',
    base_url: null,
    has_api_key: false,
    configured_credentials: false,
    credentials_satisfied: true,
    available: true,
    headers: {},
    params: {},
    category: 'web_general',
    domain: 'web',
    capabilities: ['search'],
    integration_type: 'scraper',
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    key_requirement: 'none',
    auth_requirement: 'none',
    credential_fields: [],
    optional_credential_effect: null,
    risk_level: 'low',
    risk_reasons: [],
    distribution: 'core',
    package_extra: null,
    stability: 'stable',
    usage_note: null,
    default_enabled: true,
    default_for: [],
    description: 'Custom proxy capable source',
    ...overrides,
  }
}

function warpStatus(): WarpStatus {
  return {
    status: 'disabled',
    mode: 'wireproxy',
    owner: 'none',
    socks_port: 40000,
    http_port: 0,
    ip: '',
    pid: 0,
    interface: null,
    last_error: '',
    protocol: 'socks5',
    proxy_type: 'socks5',
    available_modes: {
      wireproxy: false,
      kernel: false,
      usque: false,
      'warp-cli': false,
      external: false,
    },
  }
}

describe('SouWen Google SourcesPage accessibility', () => {
  beforeEach(() => {
    useAuthStore.setState({
      baseUrl: '',
      token: 'test-token',
      isAuthenticated: true,
      version: 'test',
      issuedAt: Date.now(),
      role: 'admin',
      features: { sources_config_read: true, sources_config_write: true },
    })
    useNotificationStore.setState({ toasts: [] })

    vi.spyOn(api, 'getDoctor').mockResolvedValue(doctorResponse([doctorSource()]))
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
    vi.spyOn(api, 'getSourcesConfig').mockResolvedValue({
      [TEST_SOURCE_NAME]: sourceConfig(),
    })
    vi.spyOn(api, 'getWarpStatus').mockResolvedValue(warpStatus())
    vi.spyOn(api, 'updateSourceConfig').mockResolvedValue({
      status: 'ok',
      source: TEST_SOURCE_NAME,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
    useAuthStore.setState({
      baseUrl: '',
      token: '',
      isAuthenticated: false,
      version: '',
      issuedAt: 0,
      role: 'guest',
      features: {},
    })
  })

  it('exposes advanced source configuration controls through accessible labels', async () => {
    const user = userEvent.setup()

    render(<SourcesPage />)

    await user.click(await screen.findByText(TEST_SOURCE_NAME))
    expect(await screen.findByLabelText('sourceConfig.proxy')).toBeInTheDocument()
    expect(screen.getByLabelText('sourceConfig.httpBackend')).toBeInTheDocument()
    expect(screen.getByLabelText('sourceConfig.baseUrl')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('sourceConfig.proxy'), 'custom')
    expect(screen.getByLabelText('sourceConfig.proxyCustom')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'sourceConfig.apiKeyReplace' }))
    expect(screen.getByLabelText('sourceConfig.apiKey')).toBeInTheDocument()
  })
})
