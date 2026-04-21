/**
 * Bilibili 中心页面 - Classic 皮肤版本
 *
 * 文件用途：B 站热门 / 排行榜 / 视频搜索 / 视频详情 / 用户信息的统一入口
 *
 * 五个 Tab：
 *   - popular: 热门视频
 *   - ranking: 排行榜（可选类型）
 *   - search: 关键词搜索
 *   - detail: 视频详情（评论 / 字幕 / AI 总结 / 相关推荐）
 *   - user: 用户信息（投稿列表）
 *
 * 业务逻辑统一抽取至 `@core/hooks/useBilibiliPage`，本文件仅保留 UI 渲染。
 */

import { m } from 'framer-motion'
import {
  Flame, Trophy, Search as SearchIcon, Play, User as UserIcon,
  Eye, ThumbsUp, MessageCircle, Coins, Star, Share2, Tv, ExternalLink,
} from 'lucide-react'
import {
  useBilibiliPage,
  RANK_TYPES,
} from '@core/hooks/useBilibiliPage'
import { fadeInUp } from '@core/lib/animations'
import styles from './BilibiliPage.module.scss'

const TABS = [
  { id: 'popular', icon: Flame, labelKey: 'bilibili.popular' },
  { id: 'ranking', icon: Trophy, labelKey: 'bilibili.ranking' },
  { id: 'search', icon: SearchIcon, labelKey: 'bilibili.search' },
  { id: 'detail', icon: Play, labelKey: 'bilibili.videoDetail' },
  { id: 'user', icon: UserIcon, labelKey: 'bilibili.userInfo' },
] as const

function thumbUrl(pic: string): string {
  if (!pic) return ''
  // Bilibili 静态图通常支持 @WxHc.webp 优化
  if (pic.includes('@')) return pic
  return `${pic}@320w_200h_1c.webp`
}

export function BilibiliPage() {
  const {
    t,
    tab, setTab,
    popularLoading, popularResults, handleLoadPopular,
    rankingLoading, rankingResults, rankType, setRankType, handleLoadRanking,
    searchLoading, searchResults, searchKeyword, setSearchKeyword, handleSearch,
    detailLoading, videoDetail, detailBvid, setDetailBvid,
    comments, commentsLoading,
    subtitles, subtitlesLoading,
    aiSummary, summaryLoading,
    related, relatedLoading,
    handleGetDetail,
    userLoading, userInfo, userMid, setUserMid,
    userVideos, userVideosLoading,
    handleGetUser,
  } = useBilibiliPage()

  const renderVideoCard = (v: {
    bvid: string
    title: string
    pic: string
    ownerName?: string
    durationStr?: string
    views?: number
    url: string
  }) => (
    <a
      key={v.bvid + v.url}
      className={styles.videoCard}
      href={v.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <div className={styles.thumbWrap}>
        {v.pic ? (
          <img className={styles.thumb} src={thumbUrl(v.pic)} alt={v.title} loading="lazy" />
        ) : (
          <div className={styles.thumbPlaceholder}>
            <Play size={32} />
          </div>
        )}
        {v.durationStr && (
          <span className={styles.durationBadge}>{v.durationStr}</span>
        )}
      </div>
      <div className={styles.cardBody}>
        <h3 className={styles.videoTitle}>{v.title}</h3>
        <div className={styles.videoSub}>
          {v.ownerName && (
            <span className={styles.channel}>
              <Tv size={12} /> {v.ownerName}
            </span>
          )}
          {typeof v.views === 'number' && v.views > 0 && (
            <span className={styles.metaItem}>
              <Eye size={12} /> {v.views.toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </a>
  )

  return (
    <div className={styles.page}>
      <m.div className={styles.hero} {...fadeInUp}>
        <h1 className={styles.heroTitle}>{t('bilibili.title')}</h1>
        <p className={styles.heroSubtitle}>{t('bilibili.subtitle')}</p>
      </m.div>

      <div className={styles.tabs} role="tablist">
        {TABS.map(({ id, icon: Icon, labelKey }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={`${styles.tab} ${tab === id ? styles.tabActive : ''}`}
            onClick={() => setTab(id)}
          >
            <Icon size={14} /> {t(labelKey)}
          </button>
        ))}
      </div>

      {/* ─── Popular ─── */}
      {tab === 'popular' && (
        <section className={styles.panel}>
          <div className={styles.controls}>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={handleLoadPopular}
              disabled={popularLoading}
            >
              {popularLoading ? t('bilibili.loading') : t('bilibili.loadPopular')}
            </button>
          </div>
          <div className={styles.grid}>
            {popularLoading && popularResults.length === 0 && (
              <div className={styles.empty}>{t('bilibili.loading')}</div>
            )}
            {!popularLoading && popularResults.length === 0 && (
              <div className={styles.empty}>{t('bilibili.noResults')}</div>
            )}
            {popularResults.map((v) =>
              renderVideoCard({
                bvid: v.bvid,
                title: v.title,
                pic: v.pic,
                ownerName: v.owner?.name,
                durationStr: v.duration_str,
                views: v.stat?.view,
                url: v.url || `https://www.bilibili.com/video/${v.bvid}`,
              }),
            )}
          </div>
        </section>
      )}

      {/* ─── Ranking ─── */}
      {tab === 'ranking' && (
        <section className={styles.panel}>
          <div className={styles.controls}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="bili-rank">{t('bilibili.rankType')}</label>
              <select
                id="bili-rank"
                className={styles.select}
                value={rankType}
                onChange={(e) => setRankType(e.target.value as typeof rankType)}
              >
                {RANK_TYPES.map((r) => (
                  <option key={r.value} value={r.value}>{t(r.labelKey)}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={handleLoadRanking}
              disabled={rankingLoading}
            >
              {rankingLoading ? t('bilibili.loading') : t('bilibili.loadRanking')}
            </button>
          </div>
          <ol className={styles.rankList}>
            {rankingLoading && rankingResults.length === 0 && (
              <li className={styles.empty}>{t('bilibili.loading')}</li>
            )}
            {!rankingLoading && rankingResults.length === 0 && (
              <li className={styles.empty}>{t('bilibili.noResults')}</li>
            )}
            {rankingResults.map((v, i) => (
              <li key={v.bvid} className={styles.rankItem}>
                <span className={styles.rankNum}>{String(i + 1).padStart(2, '0')}</span>
                <a
                  className={styles.rankLink}
                  href={v.url || `https://www.bilibili.com/video/${v.bvid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className={styles.rankTitle}>{v.title}</span>
                  <span className={styles.rankMeta}>
                    {v.owner?.name && (
                      <span className={styles.channel}>
                        <Tv size={12} /> {v.owner.name}
                      </span>
                    )}
                    {typeof v.stat?.view === 'number' && (
                      <span className={styles.metaItem}>
                        <Eye size={12} /> {v.stat.view.toLocaleString()}
                      </span>
                    )}
                    {typeof v.score === 'number' && (
                      <span className={styles.metaItem}>
                        {t('bilibili.score')}: {v.score.toLocaleString()}
                      </span>
                    )}
                  </span>
                </a>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* ─── Search ─── */}
      {tab === 'search' && (
        <section className={styles.panel}>
          <form className={styles.searchForm} onSubmit={handleSearch}>
            <div className={styles.searchInputWrap}>
              <SearchIcon size={16} className={styles.searchIcon} />
              <input
                type="text"
                className={styles.searchInput}
                placeholder={t('bilibili.keywordPlaceholder')}
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={searchLoading || !searchKeyword.trim()}
            >
              {searchLoading ? t('bilibili.loading') : t('bilibili.search')}
            </button>
          </form>
          <div className={styles.grid}>
            {searchLoading && searchResults.length === 0 && (
              <div className={styles.empty}>{t('bilibili.loading')}</div>
            )}
            {!searchLoading && searchResults.length === 0 && (
              <div className={styles.empty}>{t('bilibili.noResults')}</div>
            )}
            {searchResults.map((v) =>
              renderVideoCard({
                bvid: v.bvid,
                title: v.title,
                pic: v.pic,
                ownerName: v.owner?.name,
                durationStr: v.duration_str,
                views: v.stat?.view,
                url: v.url || `https://www.bilibili.com/video/${v.bvid}`,
              }),
            )}
          </div>
        </section>
      )}

      {/* ─── Detail ─── */}
      {tab === 'detail' && (
        <section className={styles.panel}>
          <form className={styles.searchForm} onSubmit={handleGetDetail}>
            <div className={styles.searchInputWrap}>
              <input
                type="text"
                className={styles.searchInput}
                placeholder={t('bilibili.bvidPlaceholder')}
                value={detailBvid}
                onChange={(e) => setDetailBvid(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={detailLoading || !detailBvid.trim()}
            >
              {detailLoading ? t('bilibili.loading') : t('bilibili.getDetail')}
            </button>
          </form>

          {videoDetail && (
            <div className={styles.detailBlock}>
              <div className={styles.detailHeader}>
                {videoDetail.pic && (
                  <img
                    className={styles.detailThumb}
                    src={thumbUrl(videoDetail.pic)}
                    alt={videoDetail.title}
                  />
                )}
                <div className={styles.detailMeta}>
                  <h2 className={styles.detailTitle}>{videoDetail.title}</h2>
                  {videoDetail.owner?.name && (
                    <div className={styles.detailOwner}>
                      <Tv size={14} /> {videoDetail.owner.name}
                    </div>
                  )}
                  {videoDetail.desc && (
                    <p className={styles.detailDesc}>{videoDetail.desc}</p>
                  )}
                  <a
                    className={styles.secondaryBtn}
                    href={videoDetail.url || `https://www.bilibili.com/video/${videoDetail.bvid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink size={13} /> Bilibili
                  </a>
                </div>
              </div>

              {videoDetail.stat && (
                <div className={styles.statsGrid}>
                  <div className={styles.statItem}>
                    <Eye size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.view.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.views')}</span>
                  </div>
                  <div className={styles.statItem}>
                    <ThumbsUp size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.like.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.likes')}</span>
                  </div>
                  <div className={styles.statItem}>
                    <Coins size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.coin.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.coins')}</span>
                  </div>
                  <div className={styles.statItem}>
                    <Star size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.favorite.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.favorites')}</span>
                  </div>
                  <div className={styles.statItem}>
                    <MessageCircle size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.danmaku.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.danmaku')}</span>
                  </div>
                  <div className={styles.statItem}>
                    <Share2 size={16} />
                    <span className={styles.statValue}>{videoDetail.stat.share.toLocaleString()}</span>
                    <span className={styles.statLabel}>{t('bilibili.shares')}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI Summary */}
          {videoDetail && (
            <details className={styles.subSection} open>
              <summary className={styles.subTitle}>{t('bilibili.aiSummary')}</summary>
              {summaryLoading && <div className={styles.empty}>{t('bilibili.loading')}</div>}
              {!summaryLoading && !aiSummary && (
                <div className={styles.empty}>{t('bilibili.noSummary')}</div>
              )}
              {aiSummary && (
                <div className={styles.summaryBox}>
                  {aiSummary.summary && <p className={styles.summaryText}>{aiSummary.summary}</p>}
                  {aiSummary.outline?.length > 0 && (
                    <ul className={styles.outlineList}>
                      {aiSummary.outline.map((o, i) => (
                        <li key={i} className={styles.outlineItem}>
                          <strong>{o.title}</strong>
                          {o.content && <span> — {o.content}</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </details>
          )}

          {/* Comments */}
          {videoDetail && (
            <details className={styles.subSection}>
              <summary className={styles.subTitle}>
                {t('bilibili.comments')}
                {comments.length > 0 && <span className={styles.subBadge}>{comments.length}</span>}
              </summary>
              {commentsLoading && <div className={styles.empty}>{t('bilibili.loading')}</div>}
              {!commentsLoading && comments.length === 0 && (
                <div className={styles.empty}>{t('bilibili.noResults')}</div>
              )}
              <div className={styles.commentList}>
                {comments.map((c) => (
                  <div key={c.rpid} className={styles.commentItem}>
                    {c.avatar && (
                      <img className={styles.commentAvatar} src={c.avatar} alt={c.uname} loading="lazy" />
                    )}
                    <div className={styles.commentBody}>
                      <div className={styles.commentHeader}>
                        <span className={styles.commentName}>{c.uname}</span>
                        <span className={styles.commentTime}>{c.time_str}</span>
                      </div>
                      <p className={styles.commentText}>{c.message}</p>
                      <div className={styles.commentMeta}>
                        <span><ThumbsUp size={11} /> {c.like.toLocaleString()}</span>
                        <span><MessageCircle size={11} /> {c.reply_count}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Subtitles */}
          {videoDetail && (
            <details className={styles.subSection}>
              <summary className={styles.subTitle}>{t('bilibili.subtitles')}</summary>
              {subtitlesLoading && <div className={styles.empty}>{t('bilibili.loading')}</div>}
              {!subtitlesLoading && subtitles.length === 0 && (
                <div className={styles.empty}>{t('bilibili.noSubtitles')}</div>
              )}
              {subtitles.map((sub, idx) => (
                <div key={idx} className={styles.subtitleSection}>
                  <div className={styles.subtitleHeader}>{sub.lang_doc || sub.lang}</div>
                  <div className={styles.subtitleLines}>
                    {sub.lines.map((line) => (
                      <div key={line.sid} className={styles.subtitleLine}>{line.content}</div>
                    ))}
                  </div>
                </div>
              ))}
            </details>
          )}

          {/* Related */}
          {videoDetail && (
            <details className={styles.subSection}>
              <summary className={styles.subTitle}>{t('bilibili.related')}</summary>
              {relatedLoading && <div className={styles.empty}>{t('bilibili.loading')}</div>}
              {!relatedLoading && related.length === 0 && (
                <div className={styles.empty}>{t('bilibili.noResults')}</div>
              )}
              <div className={styles.grid}>
                {related.map((v) =>
                  renderVideoCard({
                    bvid: v.bvid,
                    title: v.title,
                    pic: v.pic,
                    ownerName: v.owner?.name,
                    durationStr: v.duration_str,
                    views: v.stat?.view,
                    url: v.url || `https://www.bilibili.com/video/${v.bvid}`,
                  }),
                )}
              </div>
            </details>
          )}
        </section>
      )}

      {/* ─── User ─── */}
      {tab === 'user' && (
        <section className={styles.panel}>
          <form className={styles.searchForm} onSubmit={handleGetUser}>
            <div className={styles.searchInputWrap}>
              <input
                type="number"
                inputMode="numeric"
                className={styles.searchInput}
                placeholder={t('bilibili.midPlaceholder')}
                value={userMid}
                onChange={(e) => setUserMid(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={userLoading || !userMid.trim()}
            >
              {userLoading ? t('bilibili.loading') : t('bilibili.getUserInfo')}
            </button>
          </form>

          {userInfo && (
            <div className={styles.userCard}>
              {userInfo.face && (
                <img className={styles.userAvatar} src={userInfo.face} alt={userInfo.name} />
              )}
              <div className={styles.userBody}>
                <div className={styles.userHeader}>
                  <h2 className={styles.userName}>{userInfo.name}</h2>
                  <span className={styles.userLevel}>Lv.{userInfo.level}</span>
                  {userInfo.vip_label && (
                    <span className={styles.userVip}>{userInfo.vip_label}</span>
                  )}
                </div>
                {userInfo.sign && <p className={styles.userBio}>{userInfo.sign}</p>}
                <div className={styles.userStats}>
                  <span><strong>{userInfo.follower.toLocaleString()}</strong> {t('bilibili.fans')}</span>
                  <span><strong>{userInfo.following.toLocaleString()}</strong> {t('bilibili.following')}</span>
                  <span><strong>{userInfo.archive_count.toLocaleString()}</strong> {t('bilibili.archives')}</span>
                </div>
                {userInfo.space_url && (
                  <a
                    className={styles.secondaryBtn}
                    href={userInfo.space_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink size={13} /> Space
                  </a>
                )}
              </div>
            </div>
          )}

          {userInfo && (
            <div>
              {userVideosLoading && <div className={styles.empty}>{t('bilibili.loading')}</div>}
              {!userVideosLoading && userVideos.length === 0 && (
                <div className={styles.empty}>{t('bilibili.noResults')}</div>
              )}
              <div className={styles.grid}>
                {userVideos.map((v) =>
                  renderVideoCard({
                    bvid: v.bvid,
                    title: v.title,
                    pic: v.pic,
                    durationStr: v.length,
                    views: v.play,
                    url: v.url || `https://www.bilibili.com/video/${v.bvid}`,
                  }),
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
