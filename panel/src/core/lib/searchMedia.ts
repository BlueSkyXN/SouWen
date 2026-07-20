/**
 * 文件用途：搜索页图片/视频结果的轻量规范化。
 */

import type { ImageResult, VideoResult } from '../types'

export type SearchMediaKind = 'image' | 'video'

export interface SearchMediaItem {
  kind: SearchMediaKind
  title: string
  url: string
  thumbnailUrl: string
  source: string
  description: string
  duration: string
  meta: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object'
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function positiveNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function isImageResult(value: unknown): value is ImageResult {
  return isRecord(value) && typeof value.image_url === 'string'
}

function isVideoResult(value: unknown): value is VideoResult {
  return isRecord(value) && typeof value.thumbnail === 'string' && typeof value.url === 'string'
}

export function mediaItemFromSearchResult(
  value: unknown,
  capability: string,
): SearchMediaItem | null {
  if (capability === 'search_images' && isImageResult(value)) {
    const width = positiveNumber(value.width)
    const height = positiveNumber(value.height)
    return {
      kind: 'image',
      title: text(value.title) || text(value.image_source) || text(value.url),
      url: text(value.url),
      thumbnailUrl: text(value.thumbnail_url) || text(value.image_url),
      source: text(value.image_source) || text(value.source) || text(value.engine),
      description: text(value.image_url),
      duration: '',
      meta: width && height ? `${width} x ${height}` : '',
    }
  }

  if (capability === 'search_videos' && isVideoResult(value)) {
    return {
      kind: 'video',
      title: text(value.title) || text(value.url),
      url: text(value.url),
      thumbnailUrl: text(value.thumbnail),
      source: text(value.publisher) || text(value.source) || text(value.engine),
      description: text(value.description),
      duration: text(value.duration),
      meta: text(value.published),
    }
  }

  return null
}

export function mediaItemsFromSearchResults(
  values: unknown[],
  capability: string,
): SearchMediaItem[] {
  return values
    .map((value) => mediaItemFromSearchResult(value, capability))
    .filter((value): value is SearchMediaItem => value !== null)
}
