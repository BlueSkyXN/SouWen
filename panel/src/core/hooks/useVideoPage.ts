/**
 * 视频中心页面共享逻辑 Hook
 *
 * 抽取自 souwen-google 的 VideoPage 组件，包含 Trending / Search / Transcript
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
  BilibiliSearchItem,
} from '../types'

export type Tab = 'trending' | 'search' | 'bilibili' | 'transcript'

export const BILIBILI_ORDERS = [
  { value: 'totalrank', labelKey: 'video.bilibiliOrderDefault' },
  { value: 'click', labelKey: 'video.bilibiliOrderPlay' },
  { value: 'pubdate', labelKey: 'video.bilibiliOrderPubdate' },
  { value: 'dm', labelKey: 'video.bilibiliOrderDanmaku' },
  { value: 'stow', labelKey: 'video.bilibiliOrderFavorite' },
]

/** 修正 Bilibili API 返回的协议相对 URL（如 //i0.hdslb.com/...）为 https。 */
export function normalizeBiliUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('//')) return `https:${url}`
  return url
}

/** 去除 Bilibili 标题里的 <em class="keyword"> 高亮标签，避免 XSS。 */
export function stripHtml(s: string): string {
  if (!s) return ''
  return s.replace(/<[^>]*>/g, '')
}

/** Sanitize a Bilibili BV id (alphanumeric only). */
export function sanitizeBvid(id: string): string {
  return id.trim().replace(/[^a-zA-Z0-9]/g, '')
}

export function formatPlayCount(n: number): string {
  if (!n || n < 0) return '0'
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`
  return n.toLocaleString()
}

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

  // Bilibili search state
  const [biliQuery, setBiliQuery] = useState('')
  const [biliOrder, setBiliOrder] = useState('totalrank')
  const [biliLoading, setBiliLoading] = useState(false)
  const [biliResults, setBiliResults] = useState<BilibiliSearchItem[]>([])

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

  const handleBiliSearch = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!biliQuery.trim()) return
    const signal = cancelInflight()
    setBiliLoading(true)
    try {
      const res = await api.searchBilibili(biliQuery.trim(), 20, biliOrder, signal)
      setBiliResults(res.results ?? [])
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setBiliLoading(false)
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
    biliQuery, setBiliQuery,
    biliOrder, setBiliOrder,
    biliLoading,
    biliResults,
    handleLoadTrending,
    handleSearch,
    handleGetTranscript,
    handleBiliSearch,
    copyTranscript,
  }
}
