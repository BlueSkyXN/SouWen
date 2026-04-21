/**
 * 哔哩哔哩页面共享逻辑 Hook
 *
 * 包含 Popular / Ranking / Search / Detail / User 五个 Tab 的状态管理、
 * API 调用与中止控制器逻辑。所有皮肤的 BilibiliPage 仅负责 UI 渲染，
 * 业务逻辑统一在此处维护。
 */

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import type {
  BilibiliPopularVideo,
  BilibiliRankVideo,
  BilibiliVideoDetail,
  BilibiliUserInfo,
  BilibiliUserVideoItem,
  BilibiliComment,
  BilibiliSubtitle,
  BilibiliAISummary,
  BilibiliRelatedVideo,
} from '../types'

export type BilibiliTab = 'popular' | 'ranking' | 'search' | 'detail' | 'user'

export type BilibiliRankType = 'all' | 'origin' | 'rookie'

export const RANK_TYPES: Array<{ value: BilibiliRankType; labelKey: string }> = [
  { value: 'all', labelKey: 'bilibili.allSite' },
  { value: 'origin', labelKey: 'bilibili.origin' },
  { value: 'rookie', labelKey: 'bilibili.rookie' },
]

export function useBilibiliPage() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [tab, setTab] = useState<BilibiliTab>('popular')
  const abortRef = useRef<AbortController | null>(null)

  // Popular state
  const [popularLoading, setPopularLoading] = useState(false)
  const [popularResults, setPopularResults] = useState<BilibiliPopularVideo[]>([])

  // Ranking state
  const [rankingLoading, setRankingLoading] = useState(false)
  const [rankingResults, setRankingResults] = useState<BilibiliRankVideo[]>([])
  const [rankType, setRankType] = useState<BilibiliRankType>('all')

  // Search state
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<BilibiliVideoDetail[]>([])
  const [searchKeyword, setSearchKeyword] = useState('')

  // Detail state
  const [detailLoading, setDetailLoading] = useState(false)
  const [videoDetail, setVideoDetail] = useState<BilibiliVideoDetail | null>(null)
  const [detailBvid, setDetailBvid] = useState('')
  const [comments, setComments] = useState<BilibiliComment[]>([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [subtitles, setSubtitles] = useState<BilibiliSubtitle[]>([])
  const [subtitlesLoading, setSubtitlesLoading] = useState(false)
  const [aiSummary, setAiSummary] = useState<BilibiliAISummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [related, setRelated] = useState<BilibiliRelatedVideo[]>([])
  const [relatedLoading, setRelatedLoading] = useState(false)

  // User state
  const [userLoading, setUserLoading] = useState(false)
  const [userInfo, setUserInfo] = useState<BilibiliUserInfo | null>(null)
  const [userMid, setUserMid] = useState('')
  const [userVideos, setUserVideos] = useState<BilibiliUserVideoItem[]>([])
  const [userVideosLoading, setUserVideosLoading] = useState(false)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const cancelInflight = () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    return abortRef.current.signal
  }

  const reportError = (err: unknown) => {
    if (err instanceof Error && err.name !== 'AbortError') {
      addToast('error', err.message)
    }
  }

  const handleLoadPopular = async () => {
    const signal = cancelInflight()
    setPopularLoading(true)
    try {
      const res = await api.getBilibiliPopular(1, 20, signal)
      setPopularResults(res ?? [])
    } catch (err) {
      reportError(err)
    } finally {
      setPopularLoading(false)
    }
  }

  const handleLoadRanking = async () => {
    const signal = cancelInflight()
    setRankingLoading(true)
    try {
      const res = await api.getBilibiliRanking(0, rankType, signal)
      setRankingResults(res ?? [])
    } catch (err) {
      reportError(err)
    } finally {
      setRankingLoading(false)
    }
  }

  const handleSearch = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!searchKeyword.trim()) return
    const signal = cancelInflight()
    setSearchLoading(true)
    try {
      const res = await api.getBilibiliSearch(searchKeyword.trim(), 1, 20, signal)
      setSearchResults(res ?? [])
    } catch (err) {
      reportError(err)
    } finally {
      setSearchLoading(false)
    }
  }

  const handleGetDetail = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!detailBvid.trim()) return
    const signal = cancelInflight()
    const bvid = detailBvid.trim()
    setDetailLoading(true)
    setVideoDetail(null)
    setComments([])
    setSubtitles([])
    setAiSummary(null)
    setRelated([])
    try {
      const detail = await api.getBilibiliVideo(bvid, signal)
      setVideoDetail(detail)
      setCommentsLoading(true)
      setSubtitlesLoading(true)
      setSummaryLoading(true)
      setRelatedLoading(true)
      const [commentsRes, subtitlesRes, summaryRes, relatedRes] = await Promise.allSettled([
        api.getBilibiliComments(bvid, 1, 20, signal),
        api.getBilibiliSubtitles(bvid, signal),
        api.getBilibiliAiSummary(bvid, signal),
        api.getBilibiliRelated(bvid, signal),
      ])
      if (commentsRes.status === 'fulfilled') setComments(commentsRes.value ?? [])
      else reportError(commentsRes.reason)
      setCommentsLoading(false)

      if (subtitlesRes.status === 'fulfilled') setSubtitles(subtitlesRes.value ?? [])
      else reportError(subtitlesRes.reason)
      setSubtitlesLoading(false)

      if (summaryRes.status === 'fulfilled') setAiSummary(summaryRes.value)
      else reportError(summaryRes.reason)
      setSummaryLoading(false)

      if (relatedRes.status === 'fulfilled') setRelated(relatedRes.value ?? [])
      else reportError(relatedRes.reason)
      setRelatedLoading(false)
    } catch (err) {
      reportError(err)
      setCommentsLoading(false)
      setSubtitlesLoading(false)
      setSummaryLoading(false)
      setRelatedLoading(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleGetUser = async (e?: FormEvent) => {
    e?.preventDefault()
    const midNum = Number(userMid.trim())
    if (!midNum || Number.isNaN(midNum)) return
    const signal = cancelInflight()
    setUserLoading(true)
    setUserInfo(null)
    setUserVideos([])
    try {
      const info = await api.getBilibiliUser(midNum, signal)
      setUserInfo(info)
      setUserVideosLoading(true)
      try {
        const videos = await api.getBilibiliUserVideos(midNum, 1, 30, signal)
        setUserVideos(videos ?? [])
      } catch (err) {
        reportError(err)
      } finally {
        setUserVideosLoading(false)
      }
    } catch (err) {
      reportError(err)
    } finally {
      setUserLoading(false)
    }
  }

  return {
    t,
    tab, setTab,
    // popular
    popularLoading, popularResults, handleLoadPopular,
    // ranking
    rankingLoading, rankingResults, rankType, setRankType, handleLoadRanking,
    // search
    searchLoading, searchResults, searchKeyword, setSearchKeyword, handleSearch,
    // detail
    detailLoading, videoDetail, detailBvid, setDetailBvid,
    comments, commentsLoading,
    subtitles, subtitlesLoading,
    aiSummary, summaryLoading,
    related, relatedLoading,
    handleGetDetail,
    // user
    userLoading, userInfo, userMid, setUserMid,
    userVideos, userVideosLoading,
    handleGetUser,
  }
}
