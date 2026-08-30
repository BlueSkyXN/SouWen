import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { CalmPrecisionApp, projectSettingsForDisplay, redactForDisplay } from '../../CalmPrecisionApp'
import { assertBaseUrlAllowed } from '../services/_base'
import { adminClient } from '../services/admin-client'
import { useAuthStore } from '../stores/authStore'

const sdk = vi.hoisted(() => ({
  search: vi.fn(),
  llmSearch: vi.fn(),
  fetch: vi.fn(),
  listProviders: vi.fn(),
}))

vi.mock('@core/sdk-client', () => ({
  useSouWenClient: () => sdk,
}))

function authenticate(role: 'admin' | 'user') {
  useAuthStore.getState().setAuth('http://localhost:8000', 'test-token', '2.0.0rc6')
  useAuthStore.getState().setRole({
    role,
    features: { search: true, fetch: role === 'admin' },
    guest_enabled: false,
    user_password_set: true,
    admin_password_set: true,
    admin_open: false,
  })
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function searchPage(items: Array<Record<string, unknown>>) {
  return { items, page: { limit: 20 }, meta: {}, context: { request_id: 'test', api_major: 2 } }
}

function llmResult(answer: string | null, evidence: Array<Record<string, unknown>> = []) {
  const items = evidence.map((item, index) => ({
    id: String(item.item_id ?? `item-${index + 1}`),
    title: String(item.title_or_snippet ?? `item-${index + 1}`),
    url: item.public_url,
    provenance: [{ provider: String(item.provider ?? 'provider'), outcome: 'success' }],
  }))
  return { answer, evidence, items, meta: {}, usage: {}, query: 'query', context: { request_id: 'test', api_major: 2 } }
}

function fetchBatch(items: Array<Record<string, unknown>>) {
  return { items, meta: {}, context: { request_id: 'test', api_major: 2 } }
}

describe('Calm Precision Panel', () => {
  beforeEach(() => {
    useAuthStore.getState().logout()
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    window.location.hash = '#/search'
  })

  afterEach(() => vi.unstubAllGlobals())

  it('renders only the five Calm Precision top-level navigation groups for admins', async () => {
    authenticate('admin')
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    expect(await screen.findByRole('heading', { name: '搜索' })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: '主导航' })
    expect(navigation.getElementsByTagName('a')).toHaveLength(5)
    expect(navigation).toHaveTextContent('Search')
    expect(navigation).toHaveTextContent('LLM Search')
    expect(navigation).toHaveTextContent('Fetch')
    expect(navigation).toHaveTextContent('Providers')
    expect(navigation).toHaveTextContent('Runtime / Settings')
    expect(navigation).not.toHaveTextContent('Wayback')
    expect(navigation).not.toHaveTextContent('Bilibili')
    const skipLink = screen.getByRole('link', { name: '跳到主要内容' })
    const main = document.getElementById('main-content')
    expect(skipLink).toHaveAttribute('href', '#main-content')
    expect(main).toHaveAttribute('tabindex', '-1')
    skipLink.focus()
    await user.keyboard('{Enter}')
    expect(main).toHaveFocus()
    expect(screen.getByLabelText('切换为深色模式')).toBeVisible()
    expect(screen.getByLabelText('查询')).toBeRequired()
    expect(screen.getByRole('combobox', { name: '领域' })).toHaveValue('paper')
    expect(screen.getByRole('option', { name: 'knowledge' })).toBeInTheDocument()
  })

  it('keeps the admin-only navigation group out of a user session', async () => {
    authenticate('user')
    render(<CalmPrecisionApp />)

    const navigation = await screen.findByRole('navigation', { name: '主导航' })
    expect(navigation.getElementsByTagName('a')).toHaveLength(4)
    expect(navigation).not.toHaveTextContent('Runtime / Settings')
  })

  it('redacts secrets again before an admin response can be displayed', () => {
    expect(redactForDisplay({ api_key: 'real-value', nested: { cookie: 'x', enabled: true } })).toEqual({
      api_key: '[redacted]',
      nested: { cookie: '[redacted]', enabled: true },
    })
  })

  it('projects Settings to a safe gateway posture without legacy or secret fields', () => {
    const summary = projectSettingsForDisplay({
      admin_password: 'masked',
      proxy: 'http://private.example',
      warp_enabled: true,
      guest_enabled: false,
      expose_docs: true,
      cors_origins: ['https://panel.example'],
      trusted_proxies: ['127.0.0.1'],
      sources: { openalex: { enabled: true } },
      llm_search_gateways: { primary: { enabled: true } },
      llm: { enabled: true, protocol: 'openai_chat', model: 'test-model', api_key: 'secret' },
    })

    expect(summary).toEqual({
      access: {
        guest_enabled: false,
        docs_enabled: true,
        cors_origin_count: 1,
        trusted_proxy_count: 1,
      },
      providers: { configured_source_count: 1, llm_gateway_count: 1 },
      llm_search: { gateway_declared: true, availability_source: 'Providers' },
    })
    expect(JSON.stringify(summary)).not.toMatch(
      /admin_password|warp_enabled|api_key|private\.example|masked|secret/i,
    )
  })

  it('shows loading, error and empty states for generated-SDK search calls', async () => {
    authenticate('user')
    let resolveSearch: ((value: { items: Array<Record<string, unknown>> }) => void) | undefined
    sdk.search.mockImplementationOnce(() => new Promise((resolve) => { resolveSearch = resolve }))
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    await user.type(await screen.findByLabelText('查询'), 'test query')
    await user.click(screen.getByRole('button', { name: '运行搜索' }))
    expect(screen.getByRole('status')).toHaveTextContent('正在请求搜索结果')
    expect(sdk.search.mock.calls[0][0]).toMatchObject({ domains: ['paper'] })
    resolveSearch?.({ items: [] })
    expect(await screen.findByText('本次请求没有可显示的结果。')).toBeInTheDocument()

    sdk.search.mockRejectedValueOnce(new Error('request failed'))
    await user.click(screen.getByRole('button', { name: '运行搜索' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('request failed')
  })

  it('uses the generated domain list and leaves Provider selection to the Server', async () => {
    authenticate('user')
    sdk.search.mockResolvedValueOnce(searchPage([]))
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    await user.type(await screen.findByLabelText('查询'), 'default provider query')
    await user.selectOptions(screen.getByRole('combobox', { name: '领域' }), 'knowledge')
    await user.click(screen.getByRole('button', { name: '运行搜索' }))

    expect(sdk.search.mock.calls[0][0]).toMatchObject({ domains: ['knowledge'] })
    expect(sdk.search.mock.calls[0][0]).not.toHaveProperty('providers')
  })

  it('rejects an untrusted base URL before a token can be sent', () => {
    expect(() => assertBaseUrlAllowed('https://untrusted.example')).toThrow('白名单')
  })

  it('renders contract-shaped LLM evidence with title_or_snippet and public_url', async () => {
    authenticate('user')
    window.location.hash = '#/llm-search'
    sdk.llmSearch.mockResolvedValueOnce(llmResult('依据已汇总。[evidence-1]', [{
      id: 'evidence-1', item_id: 'item-1', provider: 'provider-a', public_url: 'https://example.test/evidence',
      retrieved_at: '2026-07-27T00:00:00Z', title_or_snippet: '规范化证据标题',
    }]))
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    await user.type(await screen.findByLabelText('问题'), 'evidence query')
    await user.type(screen.getByLabelText('Provider ID'), 'provider-a')
    await user.click(screen.getByRole('button', { name: '运行 LLM Search' }))

    expect(sdk.llmSearch.mock.calls[0][0]).toMatchObject({
      providers: [{ id: 'provider-a', kind: 'llm_search' }],
      strategy: 'single',
    })
    expect(await screen.findByRole('link', { name: '规范化证据标题' })).toHaveAttribute('href', 'https://example.test/evidence')
    expect(screen.getByText('provider-a')).toBeInTheDocument()
  })

  it('treats evidence-only LLM Search as a successful contract response', async () => {
    authenticate('user')
    window.location.hash = '#/llm-search'
    sdk.llmSearch.mockResolvedValueOnce(llmResult(null, [{
      id: 'evidence-1', item_id: 'item-1', provider: 'provider-a', public_url: 'https://example.test/evidence',
      retrieved_at: '2026-07-27T00:00:00Z', title_or_snippet: '仅证据结果',
    }]))
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    await user.type(await screen.findByLabelText('问题'), 'evidence-only query')
    await user.type(screen.getByLabelText('Provider ID'), 'provider-a')
    await user.click(screen.getByRole('button', { name: '运行 LLM Search' }))

    expect(await screen.findByRole('link', { name: '仅证据结果' })).toBeInTheDocument()
    expect(screen.getByText('当前 Provider 返回了结构化证据，但未提供可验证的综合回答。')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '回答' })).not.toBeInTheDocument()
  })

  it('rejects a Fetch batch over 20 URLs without calling the SDK', async () => {
    authenticate('user')
    window.location.hash = '#/fetch'
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    fireEvent.change(await screen.findByLabelText('URLs'), {
      target: {
        value: Array.from({ length: 21 }, (_, index) => `https://example.test/${index}`).join('\n'),
      },
    })
    await user.click(screen.getByRole('button', { name: '开始 Fetch' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('最多支持 20 个 URL')
    expect(sdk.fetch).not.toHaveBeenCalled()
  })

  it('uses the target runtime fallback Fetch strategy without exposing fanout', async () => {
    authenticate('user')
    window.location.hash = '#/fetch'
    sdk.fetch.mockResolvedValueOnce(fetchBatch([]))
    const user = userEvent.setup()
    render(<CalmPrecisionApp />)

    await user.type(await screen.findByLabelText('URLs'), 'https://example.test/article')
    expect(screen.queryByRole('option', { name: 'fanout' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '开始 Fetch' }))

    expect(sdk.fetch.mock.calls[0][0]).toMatchObject({
      targets: ['https://example.test/article'],
      strategy: 'fallback',
      policy: { respect_robots: true },
    })
  })

  it('keeps the latest Search result, aborts the replaced request, and aborts on unmount', async () => {
    authenticate('user')
    const first = deferred<ReturnType<typeof searchPage>>()
    const second = deferred<ReturnType<typeof searchPage>>()
    const third = deferred<ReturnType<typeof searchPage>>()
    sdk.search.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise)
    const user = userEvent.setup()
    const view = render(<CalmPrecisionApp />)
    const query = await screen.findByLabelText('查询')
    const form = query.closest('form')!
    await user.type(query, 'first')
    await user.click(screen.getByRole('button', { name: '运行搜索' }))
    const firstSignal = sdk.search.mock.calls[0][1].signal as AbortSignal
    await user.clear(query)
    await user.type(query, 'second')
    fireEvent.submit(form)
    const secondSignal = sdk.search.mock.calls[1][1].signal as AbortSignal
    expect(firstSignal.aborted).toBe(true)
    await act(async () => { second.resolve(searchPage([{ id: 'fresh', title: '最新 Search', provenance: [] }])) })
    expect(await screen.findByText('最新 Search')).toBeInTheDocument()
    await act(async () => { first.resolve(searchPage([{ id: 'stale', title: '过期 Search', provenance: [] }])) })
    expect(screen.queryByText('过期 Search')).not.toBeInTheDocument()
    fireEvent.submit(form)
    const thirdSignal = sdk.search.mock.calls[2][1].signal as AbortSignal
    view.unmount()
    expect(secondSignal.aborted).toBe(false)
    expect(thirdSignal.aborted).toBe(true)
  })

  it('keeps the latest LLM Search result, aborts the replaced request, and aborts on unmount', async () => {
    authenticate('user')
    window.location.hash = '#/llm-search'
    const first = deferred<ReturnType<typeof llmResult>>()
    const second = deferred<ReturnType<typeof llmResult>>()
    const third = deferred<ReturnType<typeof llmResult>>()
    sdk.llmSearch.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise)
    const user = userEvent.setup()
    const view = render(<CalmPrecisionApp />)
    const query = await screen.findByLabelText('问题')
    const form = query.closest('form')!
    await user.type(query, 'first')
    await user.type(screen.getByLabelText('Provider ID'), 'provider-a')
    await user.click(screen.getByRole('button', { name: '运行 LLM Search' }))
    const firstSignal = sdk.llmSearch.mock.calls[0][1].signal as AbortSignal
    await user.clear(query)
    await user.type(query, 'second')
    fireEvent.submit(form)
    const secondSignal = sdk.llmSearch.mock.calls[1][1].signal as AbortSignal
    expect(firstSignal.aborted).toBe(true)
    await act(async () => { second.resolve(llmResult('最新 LLM Search')) })
    expect(await screen.findByText('最新 LLM Search')).toBeInTheDocument()
    await act(async () => { first.resolve(llmResult('过期 LLM Search')) })
    expect(screen.queryByText('过期 LLM Search')).not.toBeInTheDocument()
    fireEvent.submit(form)
    const thirdSignal = sdk.llmSearch.mock.calls[2][1].signal as AbortSignal
    view.unmount()
    expect(secondSignal.aborted).toBe(false)
    expect(thirdSignal.aborted).toBe(true)
  })

  it('keeps the latest Fetch result, aborts the replaced request, and aborts on unmount', async () => {
    authenticate('user')
    window.location.hash = '#/fetch'
    const first = deferred<ReturnType<typeof fetchBatch>>()
    const second = deferred<ReturnType<typeof fetchBatch>>()
    const third = deferred<ReturnType<typeof fetchBatch>>()
    sdk.fetch.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise)
    const user = userEvent.setup()
    const view = render(<CalmPrecisionApp />)
    const targets = await screen.findByLabelText('URLs')
    const form = targets.closest('form')!
    await user.type(targets, 'https://example.test/first')
    await user.click(screen.getByRole('button', { name: '开始 Fetch' }))
    const firstSignal = sdk.fetch.mock.calls[0][1].signal as AbortSignal
    await user.clear(targets)
    await user.type(targets, 'https://example.test/second')
    fireEvent.submit(form)
    const secondSignal = sdk.fetch.mock.calls[1][1].signal as AbortSignal
    expect(firstSignal.aborted).toBe(true)
    await act(async () => { second.resolve(fetchBatch([{ target: 'https://example.test/second', title: '最新 Fetch', status: 'success', provenance: [] }])) })
    expect(await screen.findByText('最新 Fetch')).toBeInTheDocument()
    await act(async () => { first.resolve(fetchBatch([{ target: 'https://example.test/first', title: '过期 Fetch', status: 'success', provenance: [] }])) })
    expect(screen.queryByText('过期 Fetch')).not.toBeInTheDocument()
    fireEvent.submit(form)
    const thirdSignal = sdk.fetch.mock.calls[2][1].signal as AbortSignal
    view.unmount()
    expect(secondSignal.aborted).toBe(false)
    expect(thirdSignal.aborted).toBe(true)
  })

  it('uses the canonical protected admin doctor endpoint and bearer auth', async () => {
    authenticate('admin')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ total: 0, ok: 0, available: 0, degraded: 0, degraded_total: 0, failed: 0, limited: 0, warning: 0, missing_key: 0, unavailable: 0, disabled: 0, status_counts: {}, sources: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await adminClient.getDoctor()

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/admin/doctor', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
    }))
  })
})
