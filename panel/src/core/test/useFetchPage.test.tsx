/**
 * 文件用途：useFetchPage provider 选项回归测试。
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_FETCH_PROVIDER_OPTIONS,
  parseUrls,
  useFetchPage,
} from '../hooks/useFetchPage'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import type { FetchResponse, SourceInfo, SourcesResponse } from '../types'

function source(
  name: string,
  capabilities: string[],
  description = name,
  available = true,
): SourceInfo {
  return {
    name,
    domain: capabilities.includes('fetch') ? 'fetch' : 'web',
    category: capabilities.includes('fetch') ? 'fetch' : 'web_general',
    capabilities,
    description,
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: available,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: name === 'builtin' ? ['fetch:fetch'] : [],
    min_edition: 'basic',
    edition_available: available,
    edition_reason: available ? '' : 'source unavailable in current edition',
    available,
  }
}

function sourcesResponse(sources: SourceInfo[]): SourcesResponse {
  return { sources, categories: [], defaults: { 'fetch:fetch': ['builtin'] } }
}

describe('parseUrls', () => {
  it('accepts HTTP and HTTPS protocols case-insensitively', () => {
    expect(parseUrls('HTTPS://example.com\nHttp://example.org\nftp://example.net')).toEqual([
      'HTTPS://example.com',
      'Http://example.org',
    ])
  })
})

describe('useFetchPage provider options', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse([
      source('builtin', ['fetch'], 'Built-in fetcher'),
      source('jina_reader', ['fetch'], 'Jina reader'),
    ]))
    useNotificationStore.setState({ toasts: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('keeps a complete fallback provider list when sources cannot load', async () => {
    vi.spyOn(api, 'getSources').mockRejectedValue(new Error('offline'))

    const { result } = renderHook(() => useFetchPage())
    const fallbackNames = DEFAULT_FETCH_PROVIDER_OPTIONS.map((option) => option.value)

    expect(fallbackNames).toContain('arxiv_fulltext')
    expect(fallbackNames).toContain('xcrawl')
    expect(fallbackNames).toContain('scrapling')
    expect(result.current.providerOptions.map((option) => option.value)).toEqual(fallbackNames)
  })

  it('merges fetch-capable source catalog entries and plugin providers', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(
      sourcesResponse([
        source('builtin', ['fetch'], 'Built-in from API'),
        source('plugin_fetch_probe', ['fetch'], 'Runtime plugin fetcher'),
        source('search_only_probe', ['search'], 'Search-only source'),
      ]),
    )

    const { result } = renderHook(() => useFetchPage())

    await waitFor(() => {
      expect(result.current.providerOptions.some((option) => option.value === 'plugin_fetch_probe'))
        .toBe(true)
    })

    const names = result.current.providerOptions.map((option) => option.value)
    const plugin = result.current.providerOptions.find((option) => option.value === 'plugin_fetch_probe')

    expect(names[0]).toBe('builtin')
    expect(names).toContain('arxiv_fulltext')
    expect(names).toContain('plugin_fetch_probe')
    expect(names).not.toContain('search_only_probe')
    expect(plugin).toMatchObject({
      label: 'Plugin Fetch Probe',
      description: 'Runtime plugin fetcher',
    })
  })

  it('excludes providers the source catalog explicitly marks unavailable', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(
      sourcesResponse([
        source('builtin', ['fetch'], 'Built-in from API'),
        source('tavily', ['fetch'], 'Missing Tavily key', false),
        source('plugin_fetch_probe', ['fetch'], 'Disabled runtime plugin', false),
        source('search_only_probe', ['search'], 'Search-only source'),
      ]),
    )

    const { result } = renderHook(() => useFetchPage())

    await waitFor(() => {
      const names = result.current.providerOptions.map((option) => option.value)
      expect(names).not.toContain('tavily')
      expect(names).not.toContain('plugin_fetch_probe')
    })

    const names = result.current.providerOptions.map((option) => option.value)
    expect(names).toContain('builtin')
    expect(names).toContain('arxiv_fulltext')
    expect(names).not.toContain('search_only_probe')
  })

  it('replaces a selected provider when the catalog later marks it unavailable', async () => {
    let resolveSources: (value: SourcesResponse) => void = () => {}
    vi.spyOn(api, 'getSources').mockReturnValue(
      new Promise<SourcesResponse>((resolve) => {
        resolveSources = resolve
      }),
    )

    const { result } = renderHook(() => useFetchPage())

    act(() => {
      result.current.setProvider('tavily')
    })
    expect(result.current.selectedProviders).toEqual(['tavily'])

    await act(async () => {
      resolveSources(
        sourcesResponse([
          source('builtin', ['fetch'], 'Built-in from API'),
          source('tavily', ['fetch'], 'Missing Tavily key', false),
        ]),
      )
    })

    await waitFor(() => {
      expect(result.current.selectedProviders).toEqual(['builtin'])
    })
    expect(result.current.providerOptions.map((option) => option.value)).not.toContain('tavily')
  })

  it('keeps at least one selected provider and submits providers with strategy', async () => {
    const fetchResponse: FetchResponse = {
      urls: ['https://example.com'],
      results: [],
      total: 0,
      total_ok: 0,
      total_failed: 0,
      providers: ['builtin', 'jina_reader'],
      strategy: 'fanout',
      provider: null,
    }
    const fetchSpy = vi.spyOn(api, 'fetch').mockResolvedValue(fetchResponse)

    const { result } = renderHook(() => useFetchPage())

    act(() => {
      result.current.toggleProvider('builtin')
    })
    expect(result.current.selectedProviders).toEqual(['builtin'])

    act(() => {
      result.current.setUrls('https://example.com')
      result.current.toggleProvider('jina_reader')
      result.current.setStrategy('fanout')
    })
    expect(result.current.selectedProviders).toEqual(['builtin', 'jina_reader'])
    expect(result.current.strategy).toBe('fanout')

    await act(async () => {
      await result.current.handleFetch({ preventDefault: vi.fn() } as never)
    })

    expect(fetchSpy).toHaveBeenCalledWith(
      ['https://example.com'],
      'builtin',
      30,
      expect.any(Object),
      expect.objectContaining({
        providers: ['builtin', 'jina_reader'],
        strategy: 'fanout',
      }),
    )
    expect(result.current.providerSummary).toBe('builtin + jina_reader')
  })

  it('shows extractor options when any selected provider supports them', () => {
    const { result } = renderHook(() => useFetchPage())

    expect(result.current.supportsExtractOptions).toBe(true)

    act(() => {
      result.current.setProvider('jina_reader')
    })
    expect(result.current.supportsExtractOptions).toBe(false)

    act(() => {
      result.current.toggleProvider('scrapling')
    })
    expect(result.current.selectedProviders).toEqual(['jina_reader', 'scrapling'])
    expect(result.current.supportsExtractOptions).toBe(true)
  })
})
