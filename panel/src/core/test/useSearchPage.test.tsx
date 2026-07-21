/**
 * 文件用途：useSearchPage capability 分派回归测试。
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchPage, type Capability } from '../hooks/useSearchPage'
import { listFavoriteSearches, listSearchHistory } from '../lib/searchMemory'
import { api } from '../services/api'
import type {
  ImageSearchResponse,
  SearchResponse,
  SourceInfo,
  SourcesResponse,
  VideoSearchResponse,
  WebSearchResponse,
} from '../types'

function source(name: string, capabilities: Capability[], defaultFor: string[] = []): SourceInfo {
  return {
    name,
    domain: 'web',
    category: 'web_general',
    capabilities,
    description: name,
    auth_requirement: 'none',
    credential_fields: [],
    credentials_satisfied: true,
    configured_credentials: false,
    risk_level: 'low',
    stability: 'stable',
    distribution: 'core',
    default_for: defaultFor,
    min_edition: 'basic',
    edition_available: true,
    edition_reason: '',
    available: true,
  }
}

function sourcesResponse(): SourcesResponse {
  return {
    sources: [
      source('duckduckgo', ['search'], ['web:search']),
      source('duckduckgo_news', ['search_news'], ['web:search_news']),
      source('duckduckgo_images', ['search_images'], ['web:search_images']),
      source('duckduckgo_videos', ['search_videos'], ['web:search_videos']),
    ],
    categories: [],
    defaults: {
      'web:search': ['duckduckgo'],
      'web:search_news': ['duckduckgo_news'],
      'web:search_images': ['duckduckgo_images'],
      'web:search_videos': ['duckduckgo_videos'],
    },
  }
}

async function prepareWebCapability(capability: Capability, expectedSource: string) {
  const { result } = renderHook(() => useSearchPage('web'))

  await waitFor(() => {
    expect(result.current.selectedSources).toEqual(['duckduckgo'])
  })

  act(() => {
    result.current.setCapability(capability)
  })

  await waitFor(() => {
    expect(result.current.selectedSources).toEqual([expectedSource])
  })

  act(() => {
    result.current.setQuery('  graph rag  ')
  })

  return result
}

describe('useSearchPage web capabilities', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('dispatches search_news to the news endpoint service', async () => {
    const response: WebSearchResponse = {
      query: 'graph rag',
      engines: ['duckduckgo_news'],
      results: [],
      total: 0,
      meta: {},
    }
    const newsSpy = vi.spyOn(api, 'searchNews').mockResolvedValue(response)
    const webSpy = vi.spyOn(api, 'searchWeb').mockRejectedValue(new Error('wrong endpoint'))

    const result = await prepareWebCapability('search_news', 'duckduckgo_news')

    await act(async () => {
      await result.current.handleSearch()
    })

    expect(newsSpy).toHaveBeenCalledWith(
      'graph rag',
      10,
      'wt-wt',
      'moderate',
      undefined,
      expect.any(AbortSignal),
      undefined,
      'duckduckgo_news',
    )
    expect(webSpy).not.toHaveBeenCalled()
    expect(result.current.responses).toEqual([response])
  })

  it('dispatches search_images to the images endpoint service', async () => {
    const response: ImageSearchResponse = { query: 'graph rag', results: [], total: 0, meta: {} }
    const imagesSpy = vi.spyOn(api, 'searchImages').mockResolvedValue(response)
    const webSpy = vi.spyOn(api, 'searchWeb').mockRejectedValue(new Error('wrong endpoint'))

    const result = await prepareWebCapability('search_images', 'duckduckgo_images')

    await act(async () => {
      await result.current.handleSearch()
    })

    expect(imagesSpy).toHaveBeenCalledWith(
      'graph rag',
      10,
      'wt-wt',
      'moderate',
      expect.any(AbortSignal),
      undefined,
      'duckduckgo_images',
    )
    expect(webSpy).not.toHaveBeenCalled()
    expect(result.current.responses).toEqual([response])
  })

  it('dispatches search_videos to the videos endpoint service', async () => {
    const response: VideoSearchResponse = { query: 'graph rag', results: [], total: 0, meta: {} }
    const videosSpy = vi.spyOn(api, 'searchVideos').mockResolvedValue(response)
    const webSpy = vi.spyOn(api, 'searchWeb').mockRejectedValue(new Error('wrong endpoint'))

    const result = await prepareWebCapability('search_videos', 'duckduckgo_videos')

    await act(async () => {
      await result.current.handleSearch()
    })

    expect(videosSpy).toHaveBeenCalledWith(
      'graph rag',
      10,
      'wt-wt',
      'moderate',
      expect.any(AbortSignal),
      undefined,
      'duckduckgo_videos',
    )
    expect(webSpy).not.toHaveBeenCalled()
    expect(result.current.responses).toEqual([response])
  })

  it('records successful searches and toggles the current search as a favorite', async () => {
    const response: WebSearchResponse = {
      query: 'graph rag',
      engines: ['duckduckgo'],
      results: [{ title: 'Graph RAG', url: 'https://example.com', snippet: 'demo', source: 'duckduckgo', engine: 'duckduckgo' }],
      total: 1,
      meta: {},
    }
    vi.spyOn(api, 'searchWeb').mockResolvedValue(response)

    const result = await prepareWebCapability('search', 'duckduckgo')

    await act(async () => {
      await result.current.handleSearch()
    })

    expect(listSearchHistory({ domain: 'web', capability: 'search' })).toEqual([
      expect.objectContaining({
        query: 'graph rag',
        sources: ['duckduckgo'],
        resultCount: 1,
      }),
    ])

    act(() => {
      result.current.toggleCurrentFavorite()
    })

    expect(listFavoriteSearches({ domain: 'web', capability: 'search' })).toEqual([
      expect.objectContaining({
        query: 'graph rag',
        sources: ['duckduckgo'],
      }),
    ])
  })
})

describe('useSearchPage book domain', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getSources').mockResolvedValue({
      sources: [
        {
          ...source('open_library', ['search'], ['book:search']),
          domain: 'book',
          category: 'book',
        },
      ],
      categories: [],
      defaults: { 'book:search': ['open_library'] },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('selects the book default and dispatches to searchBook', async () => {
    const response: SearchResponse = {
      query: 'The Hobbit',
      sources: ['open_library'],
      total: 0,
      results: [],
    }
    const bookSpy = vi.spyOn(api, 'searchBook').mockResolvedValue(response)
    const webSpy = vi.spyOn(api, 'searchWeb').mockRejectedValue(new Error('wrong endpoint'))
    const { result } = renderHook(() => useSearchPage('book'))

    await waitFor(() => {
      expect(result.current.selectedSources).toEqual(['open_library'])
    })
    expect(result.current.supportedCapabilities).toEqual(['search'])

    act(() => {
      result.current.setQuery('  The Hobbit  ')
    })
    await act(async () => {
      await result.current.handleSearch()
    })

    expect(bookSpy).toHaveBeenCalledWith(
      'The Hobbit',
      'open_library',
      10,
      expect.any(AbortSignal),
    )
    expect(webSpy).not.toHaveBeenCalled()
    expect(result.current.responses).toEqual([response])
  })
})
