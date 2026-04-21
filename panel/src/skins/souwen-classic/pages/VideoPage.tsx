/**
 * 视频中心页面 - Classic 皮肤版本
 *
 * 文件用途：YouTube 热门视频、视频搜索和字幕提取的统一入口
 *
 * 三个 Tab：
 *   - trending: YouTube 热门视频（可选地区与分类）
 *   - search: 视频搜索（基于 /api/v1/search/videos）
 *   - transcript: 字幕提取（输入 video_id + 语言）
 */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Play, Search as SearchIcon, FileText, Copy, ExternalLink,
  Clock, Eye, ThumbsUp, MessageCircle, Tv,
} from 'lucide-react'
import { api } from '@core/services/api'
import type {
  YouTubeVideoDetail,
  TranscriptSegment,
  VideoResult,
} from '@core/types'
import { useNotificationStore } from '@core/stores/notificationStore'
import { fadeInUp } from '@core/lib/animations'
import styles from './VideoPage.module.scss'

type Tab = 'trending' | 'search' | 'transcript'

const REGIONS = [
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
const CATEGORIES = [
  { value: '', labelKey: 'video.allCategories' },
  { value: '10', labelKey: 'video.musicCategory' },
  { value: '20', labelKey: 'video.gamingCategory' },
  { value: '25', labelKey: 'video.newsCategory' },
  { value: '17', labelKey: 'video.sportsCategory' },
  { value: '24', labelKey: 'video.entertainmentCategory' },
  { value: '28', labelKey: 'video.scienceCategory' },
]

const LANGUAGES = [
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
function sanitizeVideoId(id: string): string {
  return id.trim().replace(/[^a-zA-Z0-9_-]/g, '')
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '--:--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

function formatTimestamp(start: number): string {
  return formatDuration(start)
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}

export function VideoPage() {
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

  const handleSearch = async (e?: React.FormEvent) => {
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

  const handleGetTranscript = async (e?: React.FormEvent) => {
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

  const renderVideoCard = (v: {
    id: string
    title: string
    channel: string
    durationSeconds?: number
    durationStr?: string
    views?: number
    thumbnail: string
    publishedAt?: string
    url: string
  }) => (
    <a
      key={v.id + v.url}
      className={styles.videoCard}
      href={v.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <div className={styles.thumbWrap}>
        {v.thumbnail ? (
          <img className={styles.thumb} src={v.thumbnail} alt={v.title} loading="lazy" />
        ) : (
          <div className={styles.thumbPlaceholder}>
            <Play size={32} />
          </div>
        )}
        {(v.durationStr || v.durationSeconds) && (
          <span className={styles.durationBadge}>
            {v.durationStr || formatDuration(v.durationSeconds || 0)}
          </span>
        )}
      </div>
      <div className={styles.videoMeta}>
        <h3 className={styles.videoTitle}>{v.title}</h3>
        <div className={styles.videoSub}>
          <span className={styles.channel}>
            <Tv size={12} /> {v.channel || '—'}
          </span>
          {typeof v.views === 'number' && v.views > 0 && (
            <span className={styles.metaItem}>
              <Eye size={12} /> {v.views.toLocaleString()}
            </span>
          )}
          {v.publishedAt && (
            <span className={styles.metaItem}>{formatDate(v.publishedAt)}</span>
          )}
        </div>
      </div>
    </a>
  )

  return (
    <div className={styles.page}>
      <m.div className={styles.hero} {...fadeInUp}>
        <h1 className={styles.heroTitle}>{t('video.title')}</h1>
        <p className={styles.heroSubtitle}>{t('video.subtitle')}</p>
      </m.div>

      <div className={styles.tabs} role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'trending'}
          className={`${styles.tab} ${tab === 'trending' ? styles.tabActive : ''}`}
          onClick={() => setTab('trending')}
        >
          <Play size={14} /> {t('video.trending')}
        </button>
        <button
          role="tab"
          aria-selected={tab === 'search'}
          className={`${styles.tab} ${tab === 'search' ? styles.tabActive : ''}`}
          onClick={() => setTab('search')}
        >
          <SearchIcon size={14} /> {t('video.search')}
        </button>
        <button
          role="tab"
          aria-selected={tab === 'transcript'}
          className={`${styles.tab} ${tab === 'transcript' ? styles.tabActive : ''}`}
          onClick={() => setTab('transcript')}
        >
          <FileText size={14} /> {t('video.transcript')}
        </button>
      </div>

      {tab === 'trending' && (
        <section className={styles.panel}>
          <div className={styles.controls}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="vid-region">{t('video.region')}</label>
              <select
                id="vid-region"
                className={styles.select}
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              >
                {REGIONS.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="vid-category">{t('video.category')}</label>
              <select
                id="vid-category"
                className={styles.select}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{t(c.labelKey)}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={handleLoadTrending}
              disabled={trendingLoading}
            >
              {trendingLoading ? t('video.loading') : t('video.loadTrending')}
            </button>
          </div>

          <div className={styles.grid}>
            {trendingLoading && trendingResults.length === 0 && (
              <div className={styles.empty}>{t('video.loading')}</div>
            )}
            {!trendingLoading && trendingResults.length === 0 && (
              <div className={styles.empty}>{t('video.noResults')}</div>
            )}
            {trendingResults.map((v) =>
              renderVideoCard({
                id: v.video_id,
                title: v.title,
                channel: v.channel_title,
                durationSeconds: v.duration_seconds,
                views: v.view_count,
                thumbnail: v.thumbnail_url,
                publishedAt: v.published_at,
                url: `https://www.youtube.com/watch?v=${v.video_id}`,
              })
            )}
          </div>

          {trendingResults.length > 0 && (
            <div className={styles.statsRow}>
              {trendingResults[0] && (
                <>
                  <span className={styles.statBadge}>
                    <Eye size={12} /> {t('video.views')}: {trendingResults[0].view_count.toLocaleString()}
                  </span>
                  <span className={styles.statBadge}>
                    <ThumbsUp size={12} /> {t('video.likes')}: {trendingResults[0].like_count.toLocaleString()}
                  </span>
                  <span className={styles.statBadge}>
                    <MessageCircle size={12} /> {t('video.comments')}: {trendingResults[0].comment_count.toLocaleString()}
                  </span>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {tab === 'search' && (
        <section className={styles.panel}>
          <form className={styles.searchForm} onSubmit={handleSearch}>
            <div className={styles.searchInputWrap}>
              <SearchIcon size={16} className={styles.searchIcon} />
              <input
                type="text"
                className={styles.searchInput}
                placeholder={t('video.searchPlaceholder')}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={searchLoading || !query.trim()}
            >
              {searchLoading ? t('video.loading') : t('search.button')}
            </button>
          </form>

          <div className={styles.grid}>
            {searchLoading && searchResults.length === 0 && (
              <div className={styles.empty}>{t('video.loading')}</div>
            )}
            {!searchLoading && searchResults.length === 0 && (
              <div className={styles.empty}>{t('video.noResults')}</div>
            )}
            {searchResults.map((v, i) =>
              renderVideoCard({
                id: v.url + i,
                title: v.title,
                channel: v.publisher,
                durationStr: v.duration,
                views: v.view_count,
                thumbnail: v.thumbnail,
                publishedAt: v.published,
                url: v.url,
              })
            )}
          </div>
        </section>
      )}

      {tab === 'transcript' && (
        <section className={styles.panel}>
          <form className={styles.transcriptForm} onSubmit={handleGetTranscript}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="vid-id">{t('video.videoId')}</label>
              <input
                id="vid-id"
                type="text"
                className={styles.input}
                placeholder={t('video.videoIdPlaceholder')}
                value={videoId}
                onChange={(e) => setVideoId(e.target.value)}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="vid-lang">{t('video.language')}</label>
              <select
                id="vid-lang"
                className={styles.select}
                value={lang}
                onChange={(e) => setLang(e.target.value)}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={transcriptLoading || !videoId.trim()}
            >
              {transcriptLoading ? t('video.loading') : t('video.getTranscript')}
            </button>
          </form>

          {transcriptAvailable === false && (
            <div className={styles.empty}>{t('video.transcriptNotAvailable')}</div>
          )}

          {transcriptSegments.length > 0 && (
            <>
              <div className={styles.transcriptToolbar}>
                <span className={styles.statBadge}>
                  <Clock size={12} /> {transcriptSegments.length} segments
                </span>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={copyTranscript}
                >
                  <Copy size={13} /> {t('video.copyTranscript')}
                </button>
                <a
                  className={styles.secondaryBtn}
                  href={`https://www.youtube.com/watch?v=${sanitizeVideoId(videoId)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink size={13} /> YouTube
                </a>
              </div>

              <div className={styles.transcriptList}>
                {transcriptSegments.map((seg, i) => (
                  <div key={i} className={styles.transcriptRow}>
                    <span className={styles.transcriptTime}>
                      [{formatTimestamp(seg.start)}]
                    </span>
                    <span className={styles.transcriptText}>{seg.text}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
