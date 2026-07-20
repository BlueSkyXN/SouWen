/**
 * 文件用途：useVideoPage 视频搜索源分派回归测试。
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useVideoPage } from '../hooks/useVideoPage'
import { api } from '../services/api'
import type { BilibiliSearchResponse, SourceInfo, SourcesResponse, VideoSearchResponse } from '../types'

function source(name: string, defaultFor: string[] = []): SourceInfo {
  return {
    name,
    domain: 'web',
    category: 'web_general',
    capabilities: ['search_videos'],
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
      source('duckduckgo_videos', ['web:search_videos']),
      source('custom_videos'),
      {
        ...source('disabled_videos'),
        available: false,
      },
    ],
    categories: [],
    defaults: {
      'web:search_videos': ['duckduckgo_videos'],
    },
  }
}

describe('useVideoPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('dispatches video search with the selected registry video source', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
    const response: VideoSearchResponse = {
      query: 'demo',
      results: [],
      total: 0,
      meta: {},
    }
    const searchSpy = vi.spyOn(api, 'searchVideos').mockResolvedValue(response)
    const { result } = renderHook(() => useVideoPage())

    await waitFor(() => {
      expect(result.current.availableVideoSources.map((item) => item.name)).toEqual([
        'duckduckgo_videos',
        'custom_videos',
      ])
      expect(result.current.selectedVideoSources).toEqual(['duckduckgo_videos'])
    })

    act(() => {
      result.current.setSelectedVideoSources(['custom_videos'])
      result.current.setQuery('  demo  ')
    })

    await act(async () => {
      await result.current.handleSearch()
    })

    expect(searchSpy).toHaveBeenCalledWith(
      'demo',
      20,
      'wt-wt',
      'moderate',
      expect.any(AbortSignal),
      undefined,
      'custom_videos',
    )
    expect(result.current.searchResults).toEqual([])
  })

  it('dispatches Bilibili search with the trimmed query and selected order', async () => {
    vi.spyOn(api, 'getSources').mockResolvedValue(sourcesResponse())
    const response: BilibiliSearchResponse = {
      keyword: 'demo',
      results: [
        {
          bvid: 'BV1demo',
          title: 'demo video',
          author: 'demo author',
          play: 12345,
          danmaku: 234,
          description: '',
          duration: '01:23',
          pic: '',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      order: 'pubdate',
    }
    const searchSpy = vi.spyOn(api, 'searchBilibili').mockResolvedValue(response)
    const { result } = renderHook(() => useVideoPage())

    await waitFor(() => {
      expect(result.current.selectedVideoSources).toEqual(['duckduckgo_videos'])
    })

    act(() => {
      result.current.setBiliQuery('  demo  ')
      result.current.setBiliOrder('pubdate')
    })

    await act(async () => {
      await result.current.handleBiliSearch()
    })

    expect(searchSpy).toHaveBeenCalledWith(
      'demo',
      20,
      'pubdate',
      expect.any(AbortSignal),
    )
    expect(result.current.biliResults).toEqual(response.results)
  })
})
