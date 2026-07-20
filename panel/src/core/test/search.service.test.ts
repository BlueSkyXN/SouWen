/**
 * 文件用途：search service URL 参数序列化回归测试。
 */

import { describe, expect, it, vi } from 'vitest'
import { searchMethods } from '../services/search'

describe('search service', () => {
  it('serializes news search options to /search/news', async () => {
    const request = vi.fn().mockResolvedValue({ query: 'ai news', engines: [], results: [], total: 0 })
    const signal = new AbortController().signal
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ 'Content-Type': 'application/json' }),
    }

    await searchMethods.searchNews.call(
      ctx as never,
      'ai news',
      5,
      'us-en',
      'off',
      'd',
      signal,
      9,
      'duckduckgo_news',
    )

    expect(request).toHaveBeenCalledOnce()
    const [path, options] = request.mock.calls[0]
    const url = new URL(`http://souwen.local${path}`)
    expect(url.pathname).toBe('/api/v1/search/news')
    expect(url.searchParams.get('q')).toBe('ai news')
    expect(url.searchParams.get('max_results')).toBe('5')
    expect(url.searchParams.get('region')).toBe('us-en')
    expect(url.searchParams.get('safesearch')).toBe('off')
    expect(url.searchParams.get('time_range')).toBe('d')
    expect(url.searchParams.get('timeout')).toBe('9')
    expect(url.searchParams.get('sources')).toBe('duckduckgo_news')
    expect(options).toMatchObject({
      headers: { 'Content-Type': 'application/json' },
      signal,
    })
  })

  it('serializes image search sources to /search/images', async () => {
    const request = vi.fn().mockResolvedValue({ query: 'ai image', results: [], total: 0 })
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ 'Content-Type': 'application/json' }),
    }

    await searchMethods.searchImages.call(
      ctx as never,
      'ai image',
      5,
      'us-en',
      'off',
      undefined,
      undefined,
      'duckduckgo_images',
    )

    expect(request).toHaveBeenCalledOnce()
    const [path] = request.mock.calls[0]
    const url = new URL(`http://souwen.local${path}`)
    expect(url.pathname).toBe('/api/v1/search/images')
    expect(url.searchParams.get('sources')).toBe('duckduckgo_images')
  })

  it('serializes video search sources to /search/videos', async () => {
    const request = vi.fn().mockResolvedValue({ query: 'ai video', results: [], total: 0 })
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ 'Content-Type': 'application/json' }),
    }

    await searchMethods.searchVideos.call(
      ctx as never,
      'ai video',
      5,
      'us-en',
      'off',
      undefined,
      undefined,
      'duckduckgo_videos',
    )

    expect(request).toHaveBeenCalledOnce()
    const [path] = request.mock.calls[0]
    const url = new URL(`http://souwen.local${path}`)
    expect(url.pathname).toBe('/api/v1/search/videos')
    expect(url.searchParams.get('sources')).toBe('duckduckgo_videos')
  })
})
