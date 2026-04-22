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

import { m } from 'framer-motion'
import {
  Play, Search as SearchIcon, FileText, Copy, ExternalLink,
  Clock, Eye, ThumbsUp, MessageCircle, Tv,
} from 'lucide-react'
import {
  useVideoPage,
  REGIONS, CATEGORIES, LANGUAGES,
  sanitizeVideoId, formatDuration, formatTimestamp, formatDate,
} from '@core/hooks/useVideoPage'
import { fadeInUp } from '@core/lib/animations'
import styles from './VideoPage.module.scss'

export function VideoPage() {
  const {
    t,
    tab, setTab,
    region, setRegion,
    category, setCategory,
    trendingLoading, trendingResults,
    query, setQuery,
    searchLoading, searchResults,
    videoId, setVideoId,
    lang, setLang,
    transcriptLoading, transcriptSegments, transcriptAvailable,
    handleLoadTrending, handleSearch, handleGetTranscript, copyTranscript,
  } = useVideoPage()

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
