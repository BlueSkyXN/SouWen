/**
 * 文件用途：PluginsPanel 行内操作回归测试。
 */

import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PluginsPanel } from '@core/components/Plugins/PluginsPanel'
import {
  usePluginsPage,
  type PluginBusyKey,
  type UsePluginsPageState,
} from '@core/hooks/usePluginsPage'
import type { PluginInfo } from '@core/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@core/hooks/usePluginsPage', () => ({
  usePluginsPage: vi.fn(),
}))

const plugin = (overrides: Partial<PluginInfo> = {}): PluginInfo => ({
  name: 'superweb2pdf',
  package: 'superweb2pdf',
  version: null,
  status: 'available',
  source: 'catalog',
  first_party: false,
  description: '',
  source_adapters: [],
  fetch_handlers: [],
  restart_required: false,
  ...overrides,
})

function renderPanel(plugins: PluginInfo[]): UsePluginsPageState {
  const state: UsePluginsPageState = {
    plugins,
    loading: false,
    error: null,
    restartRequired: false,
    installEnabled: true,
    healthMap: {},
    busy: new Set<PluginBusyKey>(),
    refresh: vi.fn(async () => undefined),
    enablePlugin: vi.fn(async () => undefined),
    disablePlugin: vi.fn(async () => undefined),
    checkHealth: vi.fn(async () => undefined),
    installPackage: vi.fn(async () => true),
    uninstallPackage: vi.fn(async () => true),
    reloadPlugins: vi.fn(async () => undefined),
  }
  vi.mocked(usePluginsPage).mockReturnValue(state)
  render(<PluginsPanel />)
  return state
}

describe('PluginsPanel', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('keeps install action for catalog entries that are not installed', () => {
    renderPanel([plugin()])

    expect(screen.getByRole('button', { name: 'plugins.actions.install' })).toBeInTheDocument()
  })

  it('does not show install action for available entries that already have a version', () => {
    renderPanel([plugin({ version: '1.2.3' })])

    expect(
      screen.queryByRole('button', { name: 'plugins.actions.install' }),
    ).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'plugins.reloadCatalog' })).toHaveLength(2)
  })
})
