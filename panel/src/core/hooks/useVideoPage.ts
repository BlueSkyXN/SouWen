/**
 * 视频中心页面共享逻辑 Hook
 *
 * 抽取自 souwen-classic 的 VideoPage 组件，包含 Trending / Search / Transcript
 * 三个 Tab 的状态管理、API 调用与中止控制器逻辑，以及若干工具函数与常量。
 * 所有皮肤的 VideoPage 仅负责 UI 渲染，业务逻辑统一在此处维护。
 */

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import type {
  YouTubeVideoDetail,
  TranscriptSegment,
  VideoResult,
} from '../types'

export type Tab = 'trending' | 'search' | 'transcript'

export const REGIONS = [
  { value: 'US', label: 'US' },
  { value: 'GB', label: 'GB' },
  { value: 'JP', label: 'JP' },
  { value: 'KR', label: 'KR' },
  { value: 'CN', label: 'CN' },
  { value: 'HK', label: 'HK' },
  { value: 'TW', label: 'TW' },
  { value: 'DE', label: 'DE' },
  { value: 'FR', label: 'FR' },
  { value: 'IN', label: 'IN' },
]

// YouTube 官方 categoryId 映射
export const CATEGORIES = [
  { value: '', labelKey: 'video.allCategories' },
  { value: '10', labelKey: 'video.musicCategory' },
  { value: '20', labelKey: 'video.gamingCategory' },
  { value: '25', labelKey: 'video.newsCategory' },
  { value: '17', labelKey: 'video.sportsCategory' },
  { value: '24', labelKey: 'video.entertainmentCategory' },
  { value: '28', labelKey: 'video.scienceCategory' },
]

export const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'zh', label: '中文' },
  { value: 'zh-Hans', label: '简体中文' },
  { value: 'zh-Hant', label: '繁体中文' },
  { value: 'ja', label: '日本語' },
  { value: 'ko', label: '한국어' },
  { value: 'es', label: 'Español' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
]

/** Sanitize YouTube video ID to prevent XSS via href injection */
export function sanitizeVideoId(id: string): string {
  return id.trim().replace(/[^a-zA-Z0-9_-]/g, '')
}

export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '--:--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function formatTimestamp(start: number): string {
  return formatDuration(start)
}

export function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}

export function useVideoPage() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [tab, setTab] = useState<Tab>('trending')
  const abortRef = useRef<AbortController | null>(null)

  // Trending state
  const [region, setRegion] = useState('US')
  const [category, setCategory] = useState('')
  const [trendingLoading, setTrendingLoading] = useState(false)
  const [trendingResults, setTrendingResults] = useState<YouTubeVideoDetail[]>([])

  // Search state
  const [query, setQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<VideoResult[]>([])

  // Transcript state
  const [videoId, setVideoId] = useState('')
  const [lang, setLang] = useState('en')
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[]>([])
  const [transcriptAvailable, setTranscriptAvailable] = useState<boolean | null>(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const cancelInflight = () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    return abortRef.current.signal
  }

  const handleLoadTrending = async () => {
    const signal = cancelInflight()
    setTrendingLoading(true)
    try {
      const res = await api.getYouTubeTrending(region, category, 20, signal)
      setTrendingResults(res.results ?? [])
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setTrendingLoading(false)
    }
  }

  const handleSearch = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!query.trim()) return
    const signal = cancelInflight()
    setSearchLoading(true)
    try {
      const res = await api.searchVideos(query.trim(), 20, 'wt-wt', 'moderate', signal)
      setSearchResults(res.results ?? [])
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setSearchLoading(false)
    }
  }

  const handleGetTranscript = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!videoId.trim()) return
    const signal = cancelInflight()
    setTranscriptLoading(true)
    setTranscriptSegments([])
    setTranscriptAvailable(null)
    try {
      const res = await api.getYouTubeTranscript(videoId.trim(), lang, signal)
      setTranscriptSegments(res.segments ?? [])
      setTranscriptAvailable(res.available)
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setTranscriptLoading(false)
    }
  }

  const copyTranscript = async () => {
    const text = transcriptSegments
      .map((seg) => `[${formatTimestamp(seg.start)}] ${seg.text}`)
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      addToast('success', t('video.copied'))
    } catch {
      addToast('error', t('fetch.copyFailed', '复制失败'))
    }
  }

  return {
    t,
    tab, setTab,
    region, setRegion,
    category, setCategory,
    trendingLoading,
    trendingResults,
    query, setQuery,
    searchLoading,
    searchResults,
    videoId, setVideoId,
    lang, setLang,
    transcriptLoading,
    transcriptSegments,
    transcriptAvailable,
    handleLoadTrending,
    handleSearch,
    handleGetTranscript,
    copyTranscript,
  }
}
