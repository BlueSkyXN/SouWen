/**
 * 文件用途：Apple SourcesPage 数据源配置交互回归测试。
 */

import { render, screen, waitFor } from '@testing-library/react'
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
      'common.save': '保存',
      'sourceConfig.advancedTitle': '高级配置',
      'sourceConfig.baseUrlPlaceholder': '留空使用默认地址',
      'sourceConfig.proxyCustomPlaceholder': '例如 {{example}}',
      'sources.on': '开',
      'sources.requiresUpgrade': '需升级',
      'sources.requiresUpgradeToEdition': '需升级到 {{edition}}',
    }
    const value = translations[key] ?? key
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
      variants: _variants,
      ...props
    }: MotionDivProps) => <div {...props}>{children}</div>,
  },
}))

const TEST_SOURCE_NAME = 'custom_proxy_source'
const CUSTOM_PROXY_PLACEHOLDER = /socks5:\/\/127\.0\.0\.1:1080/

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

describe('Apple SourcesPage', () => {
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

  it('submits the custom proxy URL instead of the UI sentinel value', async () => {
    const user = userEvent.setup()

    render(<SourcesPage />)

    await user.click(await screen.findByText(TEST_SOURCE_NAME))
    const proxySelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(proxySelect, 'custom')
    await user.type(
      screen.getByPlaceholderText(CUSTOM_PROXY_PLACEHOLDER),
      'socks5://127.0.0.1:1080',
    )
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(api.updateSourceConfig).toHaveBeenCalledWith(
        TEST_SOURCE_NAME,
        expect.objectContaining({ proxy: 'socks5://127.0.0.1:1080' }),
      )
    })
    expect(api.updateSourceConfig).not.toHaveBeenCalledWith(
      TEST_SOURCE_NAME,
      expect.objectContaining({ proxy: 'custom' }),
    )
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

    await user.click(screen.getByRole('button', { name: 'sourceConfig.set' }))
    expect(screen.getByLabelText('sourceConfig.apiKey')).toBeInTheDocument()
  })

  it('does not submit unchanged redacted proxy or base URL values', async () => {
    vi.mocked(api.getSourcesConfig).mockResolvedValue({
      [TEST_SOURCE_NAME]: sourceConfig({
        proxy: 'http://***@proxy.example:8080?apiKey=***&safe=1',
        base_url: 'https://source.example/search?token=***&safe=1',
      }),
    })
    const user = userEvent.setup()

    render(<SourcesPage />)

    await user.click(await screen.findByText(TEST_SOURCE_NAME))
    await screen.findByDisplayValue('http://***@proxy.example:8080?apiKey=***&safe=1')
    await screen.findByDisplayValue('https://source.example/search?token=***&safe=1')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(api.updateSourceConfig).toHaveBeenCalledWith(
        TEST_SOURCE_NAME,
        { http_backend: 'auto' },
      )
    })
    expect(api.updateSourceConfig).not.toHaveBeenCalledWith(
      TEST_SOURCE_NAME,
      expect.objectContaining({ proxy: expect.stringContaining('***') }),
    )
    expect(api.updateSourceConfig).not.toHaveBeenCalledWith(
      TEST_SOURCE_NAME,
      expect.objectContaining({ base_url: expect.stringContaining('***') }),
    )
  })

  it('refreshes form state after saved source config is reloaded', async () => {
    vi.mocked(api.getSourcesConfig).mockResolvedValueOnce({
      [TEST_SOURCE_NAME]: sourceConfig(),
    }).mockResolvedValue({
      [TEST_SOURCE_NAME]: sourceConfig({
        proxy: 'http://***@proxy.example:8080?apiKey=***&safe=1',
        base_url: 'https://source.example/search?token=***&safe=1',
      }),
    })
    const user = userEvent.setup()

    render(<SourcesPage />)

    await user.click(await screen.findByText(TEST_SOURCE_NAME))
    const proxySelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(proxySelect, 'custom')
    await user.type(
      screen.getByPlaceholderText(CUSTOM_PROXY_PLACEHOLDER),
      'http://user:secret@proxy.example:8080?apiKey=secret&safe=1',
    )
    await user.type(
      screen.getByPlaceholderText('留空使用默认地址'),
      'https://source.example/search?token=secret&safe=1',
    )
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(api.updateSourceConfig).toHaveBeenCalled()
    })
    expect(
      await screen.findByDisplayValue('http://***@proxy.example:8080?apiKey=***&safe=1'),
    ).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('https://source.example/search?token=***&safe=1'),
    ).toBeInTheDocument()
  })

  it('keeps source configuration read-only for non-admin users', async () => {
    useAuthStore.setState({
      baseUrl: '',
      token: 'test-token',
      isAuthenticated: true,
      version: 'test',
      issuedAt: Date.now(),
      role: 'user',
      features: { sources_config_read: true, sources_config_write: false },
    })
    const user = userEvent.setup()

    render(<SourcesPage />)

    await user.click(await screen.findByText(TEST_SOURCE_NAME))

    expect(api.getSourcesConfig).not.toHaveBeenCalled()
    expect(api.getWarpStatus).not.toHaveBeenCalled()
    expect(api.updateSourceConfig).not.toHaveBeenCalled()
    expect(screen.queryByText('高级配置')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '保存' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开' })).not.toBeInTheDocument()
    expect(screen.getByText('开')).toBeInTheDocument()
  })

  it('shows edition-unavailable catalog entries as upgrade required', async () => {
    vi.mocked(api.getSources).mockResolvedValue(sourcesResponse([
      sourceInfo({
        available: false,
        edition_available: false,
        min_edition: 'full',
        edition_reason: 'requires full edition',
      }),
    ]))

    render(<SourcesPage />)

    expect(await screen.findByText('需升级')).toBeInTheDocument()
    expect(screen.getByText('需升级到 full')).toBeInTheDocument()
  })
})
