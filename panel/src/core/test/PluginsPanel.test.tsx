/**
 * 文件用途：PluginsPanel 行内操作回归测试。
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

function renderPanel(
  plugins: PluginInfo[],
  overrides: Partial<UsePluginsPageState> = {},
): UsePluginsPageState {
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
    ...overrides,
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

  it('shows restart-required status from plugin mutations', () => {
    renderPanel([plugin({ status: 'loaded', version: '1.2.3' })], { restartRequired: true })

    expect(screen.getByRole('status')).toHaveTextContent('plugins.restartBanner')
  })

  it('disables install and uninstall controls when server install is disabled', () => {
    renderPanel([plugin()], { installEnabled: false })

    expect(screen.getByText('plugins.install.disabledHint')).toBeInTheDocument()
    expect(screen.getByLabelText('plugins.install.packageLabel')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'plugins.actions.install' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'plugins.install.submitInstall' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'plugins.install.submitUninstall' })).toBeDisabled()
  })

  it('wires row actions to the plugin page state handlers', async () => {
    const user = userEvent.setup()

    const loaded = plugin({
      name: 'loaded-plugin',
      package: 'loaded-plugin',
      version: '1.0.0',
      status: 'loaded',
      description: 'Loaded plugin',
    })
    const disabled = plugin({
      name: 'disabled-plugin',
      package: 'disabled-plugin',
      version: '1.0.0',
      status: 'disabled',
      description: 'Disabled plugin',
    })
    const available = plugin({
      name: 'available-plugin',
      package: 'available-plugin',
      status: 'available',
      description: 'Available plugin',
    })
    const state = renderPanel([loaded, disabled, available])

    await user.click(screen.getByRole('button', { name: 'plugins.actions.disable' }))
    await user.click(screen.getByRole('button', { name: 'plugins.actions.enable' }))
    await user.click(screen.getByRole('button', { name: 'plugins.actions.checkHealth' }))
    await user.click(screen.getByRole('button', { name: 'plugins.actions.install' }))

    expect(state.disablePlugin).toHaveBeenCalledWith('loaded-plugin')
    expect(state.enablePlugin).toHaveBeenCalledWith('disabled-plugin')
    expect(state.checkHealth).toHaveBeenCalledWith('loaded-plugin')
    expect(state.installPackage).toHaveBeenCalledWith('available-plugin')
  })

  it('opens the detail dialog, traps close focus, and closes with Escape', async () => {
    const user = userEvent.setup()
    renderPanel([
      plugin({
        status: 'loaded',
        version: '1.2.3',
        source_adapters: ['demo_adapter'],
        fetch_handlers: ['demo_fetch'],
      }),
    ])

    const detailButton = screen.getByRole('button', { name: 'plugins.actions.viewDetail' })
    await user.click(detailButton)

    expect(screen.getByRole('dialog', { name: 'plugins.detail.title' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'plugins.detail.close' })[0]).toHaveFocus()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(detailButton).toHaveFocus()
  })
})
