import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfigEditorPanel } from '@core/components/ConfigEditor'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'

vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key)
  return {
    initReactI18next: { type: '3rdParty', init: () => {} },
    useTranslation: () => ({ t }),
  }
})

type CodeMirrorProps = {
  value: string
  onChange: (value: string) => void
}

vi.mock('@uiw/react-codemirror', () => ({
  default: ({ value, onChange }: CodeMirrorProps) => (
    <textarea
      aria-label="config.sourceYamlEditor"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock('@codemirror/lang-yaml', () => ({
  yaml: () => [],
}))

vi.mock('@codemirror/view', () => ({
  EditorView: { lineWrapping: {} },
}))

vi.mock('@codemirror/theme-one-dark', () => ({
  oneDark: {},
}))

function installMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('ConfigEditorPanel accessibility', () => {
  beforeEach(() => {
    installMatchMedia()
    useNotificationStore.setState({ toasts: [] })
    vi.spyOn(api, 'getConfigYaml').mockResolvedValue({
      path: '/tmp/souwen.yaml',
      content: [
        'general:',
        '  timeout: 30',
        'server:',
        '  user_password: secret',
        '  guest_enabled: true',
      ].join('\n'),
    })
    vi.spyOn(api, 'saveConfigYaml').mockResolvedValue({
      path: '/tmp/souwen.yaml',
      content: '',
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('exposes editor tabs, section toggles and visual fields with accessible names', async () => {
    const user = userEvent.setup()

    render(<ConfigEditorPanel />)

    expect(await screen.findByRole('tablist', { name: 'config.title' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'config.editorTabSource' })).toHaveAttribute(
      'aria-selected',
      'true',
    )

    await user.click(screen.getByRole('tab', { name: 'config.editorTabVisual' }))

    expect(screen.getByRole('tabpanel', { name: 'config.editorTabVisual' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'config.editorTabVisual' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('button', { name: 'config.visualSectionGeneral' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByRole('button', { name: 'config.visualSectionServer' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByLabelText('请求超时 (秒)')).toHaveValue(30)
    expect(screen.getByLabelText('用户密码')).toHaveValue('secret')
    expect(screen.getByLabelText('允许游客访问')).toBeChecked()

    const paperSection = screen.getByRole('button', { name: 'config.visualSectionPaper' })
    expect(paperSection).toHaveAttribute('aria-expanded', 'false')

    await user.click(paperSection)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'config.visualSectionPaper' })).toHaveAttribute(
        'aria-expanded',
        'true',
      )
    })
    expect(await screen.findByLabelText('OpenAlex API Key')).toBeInTheDocument()
    expect(await screen.findByLabelText('OpenAlex Email (legacy, not sent)')).toBeInTheDocument()
  })
})
