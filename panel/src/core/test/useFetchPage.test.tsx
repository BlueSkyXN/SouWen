/**
 * 文件用途：useFetchPage provider truth 与请求行为回归测试。
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { parseUrls, useFetchPage } from '../hooks/useFetchPage'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import type { FetchResponse, SourceInfo, SourcesResponse } from '../types'

function source(
  name: string,
  capabilities: string[] = ['fetch'],
  overrides: Partial<SourceInfo> = {},
): SourceInfo {
  return {
    name,
    domain: capabilities.includes('fetch') ? 'fetch' : 'web',
    category: capabilities.includes('fetch') ? 'fetch' : 'web_general',
    capabilities,
    description: name,
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: true,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: name === 'builtin' ? ['fetch:fetch'] : [],
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    runtime_available: true,
    runtime_reason: '',
    available: true,
    ...overrides,
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
      source('builtin', ['fetch'], { description: 'Built-in fetcher' }),
      source('jina_reader', ['fetch'], { description: 'Jina reader' }),
      source('scrapling'),
    ]))
    useNotificationStore.setState({ toasts: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('fails closed when the source catalog cannot load', async () => {
    vi.spyOn(api, 'getSources').mockRejectedValue(new Error('offline'))

    const { result } = renderHook(() => useFetchPage())

    expect(result.current.providerState.status).toBe('loading')
    expect(result.current.providerOptions).toEqual([])
    expect(result.current.selectedProviders).toEqual([])

    await waitFor(() => expect(result.current.providerState.status).toBe('error'))

    act(() => result.current.setUrls('https://example.com'))
    expect(result.current.providerOptions).toEqual([])
    expect(result.current.canFetch).toBe(false)
  })

  it('marks older catalog responses without runtime evidence unknown and disabled', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse([
      source('builtin', ['fetch'], { runtime_available: undefined }),
      source('jina_reader', ['fetch'], { runtime_available: undefined }),
    ]))

    const { result } = renderHook(() => useFetchPage())

    await waitFor(() => expect(result.current.providerState.status).toBe('error'))

    expect(result.current.providerOptions.map((option) => option.value)).toEqual([
      'builtin',
      'jina_reader',
    ])
    expect(result.current.providerOptions.every((option) => (
      option.availability === 'unknown' && !option.available
    ))).toBe(true)
    expect(result.current.selectedProviders).toEqual([])
  })

  it('shows edition, runtime, credential and static availability as distinct axes', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse([
      source('builtin'),
      source('tavily', ['fetch'], {
        min_edition: 'full',
        edition_available: false,
        edition_reason: 'requires full',
      }),
      source('scrapling', ['fetch'], {
        runtime_available: false,
        runtime_reason: 'scrapling import failed',
      }),
      source('firecrawl', ['fetch'], {
        auth_requirement: 'required',
        credential_fields: ['api_key'],
        credentials_satisfied: false,
      }),
      source('plugin_fetch_probe', ['fetch'], { available: false }),
      source('search_only_probe', ['search']),
    ]))

    const { result } = renderHook(() => useFetchPage())

    await waitFor(() => expect(result.current.providerState.status).toBe('ready'))

    expect(result.current.providerOptions.map((option) => option.value)).toEqual([
      'builtin',
      'tavily',
      'firecrawl',
      'scrapling',
      'plugin_fetch_probe',
    ])
    expect(Object.fromEntries(result.current.providerOptions.map((option) => [
      option.value,
      option.availability,
    ]))).toEqual({
      builtin: 'available',
      tavily: 'edition',
      firecrawl: 'credentials',
      scrapling: 'runtime',
      plugin_fetch_probe: 'unavailable',
    })
    expect(result.current.selectedProviders).toEqual(['builtin'])

    act(() => result.current.setProvider('scrapling'))
    expect(result.current.selectedProviders).toEqual(['builtin'])
  })

  it('uses catalog metadata for runtime-ready plugin providers without static fallback entries', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse([
      source('builtin'),
      source('plugin_fetch_probe', ['fetch'], { description: 'Runtime plugin fetcher' }),
    ]))

    const { result } = renderHook(() => useFetchPage())

    await waitFor(() => {
      expect(result.current.providerOptions.some((option) => (
        option.value === 'plugin_fetch_probe'
      ))).toBe(true)
    })

    expect(result.current.providerOptions.map((option) => option.value)).toEqual([
      'builtin',
      'plugin_fetch_probe',
    ])
    expect(result.current.providerOptions.find((option) => (
      option.value === 'plugin_fetch_probe'
    ))).toMatchObject({
      label: 'Plugin Fetch Probe',
      description: 'Runtime plugin fetcher',
      available: true,
      availability: 'available',
    })
  })

  it('keeps at least one selected provider and submits verified providers with strategy', async () => {
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
    await waitFor(() => expect(result.current.selectedProviders).toEqual(['builtin']))

    act(() => result.current.toggleProvider('builtin'))
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

  it('shows extractor options only for verified selected providers that support them', async () => {
    const { result } = renderHook(() => useFetchPage())
    await waitFor(() => expect(result.current.selectedProviders).toEqual(['builtin']))

    expect(result.current.supportsExtractOptions).toBe(true)

    act(() => result.current.setProvider('jina_reader'))
    expect(result.current.supportsExtractOptions).toBe(false)

    act(() => result.current.toggleProvider('scrapling'))
    expect(result.current.selectedProviders).toEqual(['jina_reader', 'scrapling'])
    expect(result.current.supportsExtractOptions).toBe(true)
  })
})
