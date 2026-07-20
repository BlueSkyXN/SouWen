/**
 * 文件用途：搜索媒体结果规范化回归测试。
 */

import { describe, expect, it } from 'vitest'
import { mediaItemFromSearchResult, mediaItemsFromSearchResults } from '../lib/searchMedia'
import type { ImageResult, VideoResult, WebResult } from '../types'

describe('mediaItemFromSearchResult', () => {
  it('normalizes image search results with thumbnails and dimensions', () => {
    const result: ImageResult = {
      source: 'duckduckgo_images',
      title: 'Architecture diagram',
      url: 'https://example.com/page',
      image_url: 'https://img.example/full.jpg',
      thumbnail_url: 'https://img.example/thumb.jpg',
      width: 1200,
      height: 800,
      image_source: 'example.com',
      engine: 'duckduckgo_images',
    }

    expect(mediaItemFromSearchResult(result, 'search_images')).toEqual({
      kind: 'image',
      title: 'Architecture diagram',
      url: 'https://example.com/page',
      thumbnailUrl: 'https://img.example/thumb.jpg',
      source: 'example.com',
      description: 'https://img.example/full.jpg',
      duration: '',
      meta: '1200 x 800',
    })
  })

  it('normalizes video search results with thumbnails and duration', () => {
    const result: VideoResult = {
      source: 'duckduckgo_videos',
      title: 'System demo',
      url: 'https://video.example/watch',
      duration: '03:21',
      publisher: 'Demo Channel',
      published: '2026-06-28',
      description: 'Short demo',
      thumbnail: 'https://img.example/video.jpg',
      embed_url: '',
      view_count: 42,
      engine: 'duckduckgo_videos',
    }

    expect(mediaItemFromSearchResult(result, 'search_videos')).toEqual({
      kind: 'video',
      title: 'System demo',
      url: 'https://video.example/watch',
      thumbnailUrl: 'https://img.example/video.jpg',
      source: 'Demo Channel',
      description: 'Short demo',
      duration: '03:21',
      meta: '2026-06-28',
    })
  })

  it('does not treat normal web results as media results', () => {
    const result: WebResult = {
      source: 'duckduckgo',
      title: 'Normal web page',
      url: 'https://example.com',
      snippet: 'Snippet',
      engine: 'duckduckgo',
    }

    expect(mediaItemFromSearchResult(result, 'search')).toBeNull()
    expect(mediaItemFromSearchResult(result, 'search_images')).toBeNull()
  })

  it('filters mixed results when normalizing a media result list', () => {
    const image: ImageResult = {
      source: 'duckduckgo_images',
      title: 'Architecture diagram',
      url: 'https://example.com/page',
      image_url: 'https://img.example/full.jpg',
      thumbnail_url: 'https://img.example/thumb.jpg',
      width: 1200,
      height: 800,
      image_source: 'example.com',
      engine: 'duckduckgo_images',
    }
    const web: WebResult = {
      source: 'duckduckgo',
      title: 'Normal web page',
      url: 'https://example.com',
      snippet: 'Snippet',
      engine: 'duckduckgo',
    }

    expect(mediaItemsFromSearchResults([image, web], 'search_images')).toEqual([
      expect.objectContaining({ kind: 'image', title: 'Architecture diagram' }),
    ])
  })
})
