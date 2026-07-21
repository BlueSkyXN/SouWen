/**
 * 文件用途：Carbon 皮肤的搜索页面（v1 单 domain 版）。
 * 详见 useSearchPage hook：query/sources/loading/error 由 hook 集中管理；本组件只负责 UI。
 */

import { useEffect, useRef, useState, type ComponentType } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  FileText, Users, Calendar, Link, Building, Globe,
  Cpu, ExternalLink,
  List, LayoutGrid, Grid3X3, Download,
  Shield, Zap, MessageCircle, Code2, BookOpen, Play,
} from 'lucide-react'
import { useNotificationStore } from '@core/stores/notificationStore'
import { normalizePaper, normalizePatent, normalizeWeb } from '@core/lib/normalize'
import { extractDomain } from '@core/lib/url'
import { exportMediaResults, exportPapers, exportPatents, exportWebResults, type ExportFormat } from '@core/lib/export'
import { mediaItemFromSearchResult, mediaItemsFromSearchResults } from '@core/lib/searchMedia'
import { SearchMemoryPanel } from '@core/components/SearchMemoryPanel'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import { useSearchPage, type Domain, type SearchPageResponse } from '@core/hooks/useSearchPage'
import type {
  SearchResponse,
  WebResult, PaperResult, PatentResult, BookResult,
} from '@core/types'
import styles from './SearchPage.module.scss'

type LayoutMode = 'list' | 'card' | 'grid'

const DISPLAY_DOMAINS: Domain[] = [
  'book', 'paper', 'patent', 'web', 'cn_tech', 'social', 'developer', 'knowledge', 'video',
]

const DOMAIN_ICONS: Record<Domain, ComponentType<{ size?: number }>> = {
  book: BookOpen,
  paper: FileText,
  patent: Shield,
  web: Globe,
  cn_tech: Zap,
  social: MessageCircle,
  developer: Code2,
  knowledge: BookOpen,
  video: Play,
  office: FileText,
  archive: FileText,
}

function flattenItems(domain: Domain, responses: SearchPageResponse[]): unknown[] {
  if (domain === 'book' || domain === 'paper' || domain === 'patent') {
    return (responses as SearchResponse[]).flatMap((r) => r.results.flatMap((s) => s.results))
  }
  return responses.flatMap((r): unknown[] => r.results ?? [])
}

function totalCountOf(_domain: Domain, responses: SearchPageResponse[]): number {
  return responses.reduce((sum, r) => sum + (r.total ?? 0), 0)
}

export function SearchPage() {
  const { t } = useTranslation()
  const { domain: urlDomain } = useParams<{ domain: string }>()
  const initialDomain = (DISPLAY_DOMAINS.includes(urlDomain as Domain) ? urlDomain : 'paper') as Domain
  const [domain, setDomain] = useState<Domain>(initialDomain)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('card')
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    query, setQuery,
    capability, setCapability, supportedCapabilities,
    responses, loading, error,
    availableSources, selectedSources, toggleSource,
    handleSearch,
    searchHistory, favoriteSearches, canFavoriteCurrentSearch, isCurrentFavorite,
    applySearchMemory, toggleCurrentFavorite, removeFavoriteSearch, clearCurrentSearchHistory,
  } = useSearchPage(domain)

  const addToast = useNotificationStore((s) => s.addToast)
  const SEARCH_SUGGESTIONS = [
    t('search.suggestion1'), t('search.suggestion2'), t('search.suggestion3'),
    t('search.suggestion4'), t('search.suggestion5'), t('search.suggestion6'),
  ]

  useEffect(() => {
    if (urlDomain && DISPLAY_DOMAINS.includes(urlDomain as Domain) && urlDomain !== domain) {
      setDomain(urlDomain as Domain)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlDomain])

  const prevLoadingRef = useRef(false)
  useEffect(() => {
    if (prevLoadingRef.current && !loading) {
      if (error) addToast('error', t('search.failed', { message: error.message }))
      else if (responses.length > 0) addToast('success', t('search.success', { count: totalCountOf(domain, responses) }))
    }
    prevLoadingRef.current = loading
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading])

  const canSearch = query.trim().length > 0 && selectedSources.length > 0
  const items = flattenItems(domain, responses)
  const hasResults = responses.length > 0
  const memoryClasses = {
    root: styles.memorySection,
    header: styles.memoryHeader,
    title: styles.memoryTitle,
    actions: styles.memoryActions,
    actionButton: styles.memoryActionBtn,
    groups: styles.memoryGroups,
    group: styles.memoryGroup,
    groupTitle: styles.memoryGroupTitle,
    chips: styles.memoryChips,
    chip: styles.memoryChip,
    chipText: styles.memoryChipText,
    chipMeta: styles.memoryChipMeta,
    removeButton: styles.memoryRemoveBtn,
    empty: styles.memoryEmpty,
  }

  const renderPaperCard = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    const key = p.doi || `paper-${p.source}-${i}`
    return (
      <m.article key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.cardHeader}>
          <h3 className={styles.resultTitle}>
            {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (p.title || t('search.untitled'))}
          </h3>
          {p.source && <span className={styles.sourceBadge}>{p.source}</span>}
        </div>
        <div className={styles.resultMeta}>
          {p.authors.length > 0 && <span><Users size={12} /> {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? t('search.andMore') : ''}</span>}
          {p.year && <span><Calendar size={12} /> {p.year}</span>}
          {p.doi && <span><Link size={12} /> {p.doi}</span>}
        </div>
        {p.abstract && <p className={styles.resultAbstract}>{p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}</p>}
      </m.article>
    )
  }

  const renderPatentCard = (raw: PatentResult, i: number) => {
    const p = normalizePatent(raw)
    const key = p.patentNumber || `patent-${p.source}-${i}`
    return (
      <m.article key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.cardHeader}>
          <h3 className={styles.resultTitle}>
            {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (p.title || t('search.untitled'))}
          </h3>
          {p.source && <span className={styles.sourceBadge}>{p.source}</span>}
        </div>
        <div className={styles.resultMeta}>
          {p.patentNumber && <span><FileText size={12} /> {p.patentNumber}</span>}
          {p.applicant && <span><Building size={12} /> {p.applicant}</span>}
          {p.publicationDate && <span><Calendar size={12} /> {p.publicationDate}</span>}
        </div>
        {p.abstract && <p className={styles.resultAbstract}>{p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}</p>}
      </m.article>
    )
  }

  const renderWebCard = (raw: WebResult, i: number) => {
    const item = normalizeWeb(raw)
    const key = item.url || `web-${item.source}-${i}`
    const dom = item.url ? extractDomain(item.url) : ''
    return (
      <m.article key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.cardHeader}>
          <h3 className={styles.resultTitle}>
            {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ExternalLink size={12} className={styles.externalIcon} /></a> : item.title}
          </h3>
          {(item.source || raw.engine) && <span className={styles.sourceBadge}>{item.source || raw.engine}</span>}
        </div>
        {item.url && <div className={styles.resultUrl} title={item.url}><Globe size={12} /> {dom}</div>}
        {item.snippet && <p className={styles.resultAbstract}>{item.snippet}</p>}
      </m.article>
    )
  }

  const renderMediaCard = (raw: unknown, i: number) => {
    const media = mediaItemFromSearchResult(raw, capability)
    if (!media) return null
    const key = media.url || `${media.kind}-${i}`
    const dom = media.url ? extractDomain(media.url) : ''
    return (
      <m.article key={key} className={`${styles.resultCard} ${styles.mediaResultCard}`} variants={staggerItem}>
        <a
          className={styles.mediaThumbLink}
          href={media.url || media.thumbnailUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={media.title}
        >
          {media.thumbnailUrl ? (
            <img className={styles.mediaThumb} src={media.thumbnailUrl} alt={media.title} loading="lazy" />
          ) : (
            <div className={styles.mediaPlaceholder}>
              {media.kind === 'video' ? <Play size={30} /> : <Globe size={30} />}
            </div>
          )}
          {media.duration && <span className={styles.mediaDuration}>{media.duration}</span>}
        </a>
        <div className={styles.mediaBody}>
          <div className={styles.cardHeader}>
            <h3 className={styles.resultTitle}>
              {media.url ? (
                <a href={media.url} target="_blank" rel="noopener noreferrer">
                  {media.title || t('search.untitled')}
                  <ExternalLink size={12} className={styles.externalIcon} />
                </a>
              ) : (media.title || t('search.untitled'))}
            </h3>
            {media.source && <span className={styles.sourceBadge}>{media.source}</span>}
          </div>
          <div className={styles.resultMeta}>
            {dom && <span><Globe size={12} /> {dom}</span>}
            {media.meta && <span>{media.meta}</span>}
          </div>
          {media.description && <p className={styles.resultAbstract}>{media.description}</p>}
        </div>
      </m.article>
    )
  }

  const renderItemCard = (item: unknown, i: number) => {
    if (domain === 'book') {
      const book = item as BookResult
      return (
        <m.article key={book.source_record_id || `book-${i}`} className={styles.resultCard} variants={staggerItem}>
          <div className={styles.cardHeader}>
            <h3 className={styles.resultTitle}>
              <a href={book.source_url} target="_blank" rel="noopener noreferrer">
                {book.title}
                <ExternalLink size={12} className={styles.externalIcon} />
              </a>
            </h3>
            <span className={styles.sourceBadge}>{book.source}</span>
          </div>
          <div className={styles.resultMeta}>
            {book.authors.length > 0 && <span>{book.authors.map((author) => author.name).join(', ')}</span>}
            {book.first_publish_year && <span>{book.first_publish_year}</span>}
          </div>
          {book.subjects.length > 0 && <p className={styles.resultAbstract}>{book.subjects.slice(0, 3).join(' · ')}</p>}
        </m.article>
      )
    }
    if (domain === 'paper') return renderPaperCard(item as PaperResult, i)
    if (domain === 'patent') return renderPatentCard(item as PatentResult, i)
    const mediaCard = renderMediaCard(item, i)
    if (mediaCard) return mediaCard
    return renderWebCard(item as WebResult, i)
  }

  const renderItemListItem = (item: unknown, i: number) => {
    if (domain === 'book') {
      const book = item as BookResult
      const key = book.source_record_id || `book-list-${book.source}-${i}`
      const authorStr = book.authors.slice(0, 3).map((author) => author.name).join(', ')
      const subjects = book.subjects.slice(0, 3).join(' · ')
      const dom = extractDomain(book.source_url)
      return (
        <div key={key} className={styles.resultListItem}>
          {book.source && <span className={styles.badge}>{book.source}</span>}
          <span className={styles.listTitle}>
            <a href={book.source_url} target="_blank" rel="noopener noreferrer">
              {book.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          </span>
          {authorStr && <span className={styles.listMeta}>— {authorStr}</span>}
          {book.first_publish_year && <span className={styles.listMeta}>— {book.first_publish_year}</span>}
          {subjects && <span className={styles.listMeta}>— {subjects}</span>}
          {dom && <span className={styles.listDomain} title={book.source_url}>— {dom}</span>}
        </div>
      )
    }
    if (domain === 'paper') {
      const p = normalizePaper(item as PaperResult)
      const key = p.doi || `paper-list-${p.source}-${i}`
      const dom = p.url ? extractDomain(p.url) : ''
      const authorStr = p.authors.slice(0, 3).join(', ') + (p.authors.length > 3 ? '…' : '')
      return (
        <div key={key} className={styles.resultListItem}>
          {p.source && <span className={styles.badge}>{p.source}</span>}
          <span className={styles.listTitle}>
            {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (p.title || t('search.untitled'))}
          </span>
          {authorStr && <span className={styles.listMeta}>— {authorStr}</span>}
          {p.year && <span className={styles.listMeta}>— {p.year}</span>}
          {dom && <span className={styles.listDomain} title={p.url}>— {dom}</span>}
        </div>
      )
    }
    if (domain === 'patent') {
      const p = normalizePatent(item as PatentResult)
      const key = p.patentNumber || `patent-list-${p.source}-${i}`
      const dom = p.url ? extractDomain(p.url) : ''
      return (
        <div key={key} className={styles.resultListItem}>
          {p.source && <span className={styles.badge}>{p.source}</span>}
          <span className={styles.listTitle}>
            {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (p.title || t('search.untitled'))}
          </span>
          {p.patentNumber && <span className={styles.listMeta}>— {p.patentNumber}</span>}
          {p.applicant && <span className={styles.listMeta}>— {p.applicant}</span>}
          {p.publicationDate && <span className={styles.listMeta}>— {p.publicationDate}</span>}
          {dom && <span className={styles.listDomain} title={p.url}>— {dom}</span>}
        </div>
      )
    }
    const media = mediaItemFromSearchResult(item, capability)
    if (media) {
      const key = media.url || `media-list-${i}`
      const dom = media.url ? extractDomain(media.url) : ''
      return (
        <div key={key} className={styles.resultListItem}>
          {media.source && <span className={styles.badge}>{media.source}</span>}
          <span className={styles.listTitle}>
            {media.url ? <a href={media.url} target="_blank" rel="noopener noreferrer">{media.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (media.title || t('search.untitled'))}
          </span>
          {dom && <span className={styles.listDomain} title={media.url}>— {dom}</span>}
          {media.duration && <span className={styles.listMeta}>— {media.duration}</span>}
          {media.meta && <span className={styles.listMeta}>— {media.meta}</span>}
        </div>
      )
    }
    const w = item as WebResult
    const wn = normalizeWeb(w)
    const key = wn.url || `web-list-${wn.source}-${i}`
    const dom = wn.url ? extractDomain(wn.url) : ''
    const snippet = wn.snippet.length > 80 ? wn.snippet.slice(0, 80) + '…' : wn.snippet
    return (
      <div key={key} className={styles.resultListItem}>
        {(wn.source || w.engine) && <span className={styles.badge}>{wn.source || w.engine}</span>}
        <span className={styles.listTitle}>
          {wn.url ? <a href={wn.url} target="_blank" rel="noopener noreferrer">{wn.title}<ExternalLink size={12} className={styles.externalIcon} /></a> : wn.title}
        </span>
        {dom && <span className={styles.listDomain} title={wn.url}>— {dom}</span>}
        {snippet && <span className={styles.listMeta}>— {snippet}</span>}
      </div>
    )
  }

  const renderItemGridCard = (item: unknown, i: number) => {
    if (domain === 'book') {
      const book = item as BookResult
      const authors = book.authors.slice(0, 3).map((author) => author.name).join(', ')
      const subjects = book.subjects.slice(0, 3).join(' · ')
      const summary = [authors, book.first_publish_year?.toString(), subjects].filter(Boolean).join(' · ')
      const dom = extractDomain(book.source_url)
      return (
        <m.article key={book.source_record_id || `book-grid-${i}`} className={styles.resultGridCard} variants={staggerItem}>
          <div className={styles.gridCardHeader}>
            {book.source && <span className={styles.badge}>{book.source}</span>}
            {dom && <span className={styles.gridDomain} title={book.source_url}><Globe size={11} /> {dom}</span>}
          </div>
          <h3 className={styles.gridCardTitle}>
            <a href={book.source_url} target="_blank" rel="noopener noreferrer">
              {book.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          </h3>
          {summary && <p className={styles.gridCardAbstract}>{summary}</p>}
        </m.article>
      )
    }
    const media = mediaItemFromSearchResult(item, capability)
    if (media) {
      const key = media.url || `${media.kind}-grid-${i}`
      const dom = media.url ? extractDomain(media.url) : ''
      return (
        <m.article key={key} className={`${styles.resultGridCard} ${styles.mediaGridCard}`} variants={staggerItem}>
          <a className={styles.gridMediaThumbLink} href={media.url || media.thumbnailUrl} target="_blank" rel="noopener noreferrer">
            {media.thumbnailUrl ? (
              <img className={styles.gridMediaThumb} src={media.thumbnailUrl} alt={media.title} loading="lazy" />
            ) : (
              <div className={styles.mediaPlaceholder}>
                {media.kind === 'video' ? <Play size={28} /> : <Globe size={28} />}
              </div>
            )}
            {media.duration && <span className={styles.mediaDuration}>{media.duration}</span>}
          </a>
          <div className={styles.gridCardHeader}>
            {media.source && <span className={styles.badge}>{media.source}</span>}
            {dom && <span className={styles.gridDomain} title={media.url}><Globe size={11} /> {dom}</span>}
          </div>
          <h3 className={styles.gridCardTitle}>
            {media.url ? <a href={media.url} target="_blank" rel="noopener noreferrer">{media.title || t('search.untitled')}<ExternalLink size={12} className={styles.externalIcon} /></a> : (media.title || t('search.untitled'))}
          </h3>
          {media.meta && <p className={styles.gridCardAbstract}>{media.meta}</p>}
        </m.article>
      )
    }
    let title = '', url = '', source = '', abstract = ''
    if (domain === 'paper') {
      const p = normalizePaper(item as PaperResult)
      title = p.title || t('search.untitled'); url = p.url; source = p.source; abstract = p.abstract || ''
    } else if (domain === 'patent') {
      const p = normalizePatent(item as PatentResult)
      title = p.title || t('search.untitled'); url = p.url; source = p.source; abstract = p.abstract || ''
    } else {
      const w = item as WebResult
      const wn = normalizeWeb(w)
      title = wn.title; url = wn.url; source = wn.source || w.engine; abstract = wn.snippet
    }
    const key = url || `${domain}-grid-${source}-${i}`
    const dom = url ? extractDomain(url) : ''
    return (
      <m.article key={key} className={styles.resultGridCard} variants={staggerItem}>
        <div className={styles.gridCardHeader}>
          {source && <span className={styles.badge}>{source}</span>}
          {dom && <span className={styles.gridDomain} title={url}><Globe size={11} /> {dom}</span>}
        </div>
        <h3 className={styles.gridCardTitle}>
          {url ? <a href={url} target="_blank" rel="noopener noreferrer">{title}<ExternalLink size={12} className={styles.externalIcon} /></a> : title}
        </h3>
        {abstract && <p className={styles.gridCardAbstract}>{abstract}</p>}
      </m.article>
    )
  }

  const handleExport = (format: ExportFormat) => {
    let exportedCount = 0
    if (domain === 'paper') { const list = (items as PaperResult[]).map(normalizePaper); exportedCount = list.length; exportPapers(list, format) }
    else if (domain === 'patent') { const list = (items as PatentResult[]).map(normalizePatent); exportedCount = list.length; exportPatents(list, format) }
    else if (capability === 'search_images' || capability === 'search_videos') { const list = mediaItemsFromSearchResults(items, capability); exportedCount = list.length; exportMediaResults(list, format) }
    else { const list = (items as WebResult[]).map(normalizeWeb); exportedCount = list.length; exportWebResults(list, format) }
    if (exportedCount > 0) addToast('success', t('search.exported', { count: exportedCount }))
  }

  const renderToolbar = (totalCount: number) => (
    <div className={styles.resultsToolbar}>
      <div className={styles.resultCount}>{t('search.resultCount', { count: totalCount })}</div>
      <div className={styles.toolbarActions}>
        <div className={styles.layoutToggle} role="group" aria-label={t('search.layoutCard')}>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'list' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('list')} aria-label={t('search.layoutList')}><List size={14} /></button>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'card' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('card')} aria-label={t('search.layoutCard')}><LayoutGrid size={14} /></button>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'grid' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('grid')} aria-label={t('search.layoutGrid')}><Grid3X3 size={14} /></button>
        </div>
        <div className={styles.exportGroup} role="group" aria-label={t('search.exportTitle')}>
          <button type="button" className={styles.exportBtn} onClick={() => handleExport('csv')}><Download size={13} /> {t('search.exportCSV')}</button>
          <button type="button" className={styles.exportBtn} onClick={() => handleExport('xls')}><Download size={13} /> {t('search.exportXLS')}</button>
          <button type="button" className={styles.exportBtn} onClick={() => handleExport('markdown')}><Download size={13} /> {t('search.exportMarkdown')}</button>
        </div>
      </div>
    </div>
  )

  const renderResults = () => {
    if (loading) {
      return (
        <div role="status" aria-live="polite" aria-busy="true">
          <div className={styles.searchingHint}>{t('search.searchingHint')}</div>
          {Array.from({ length: 4 }, (_, i) => <div key={i} className={styles.skeletonCard} />)}
        </div>
      )
    }
    if (error) {
      return (
        <div className={styles.errorState}>
          <p>{error.message}</p>
          <button type="button" className={styles.retryBtn} onClick={() => handleSearch()}>{t('search.retrySearch')}</button>
        </div>
      )
    }
    if (!hasResults) return null
    if (items.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
    const total = totalCountOf(domain, responses)
    if (layoutMode === 'list') {
      return <div>{renderToolbar(total)}<div className={styles.resultList}>{items.map(renderItemListItem)}</div></div>
    }
    if (layoutMode === 'grid') {
      return <div>{renderToolbar(total)}<m.div className={styles.resultGrid} variants={staggerContainer} initial="initial" animate="animate">{items.map(renderItemGridCard)}</m.div></div>
    }
    return <m.div variants={staggerContainer} initial="initial" animate="animate">{renderToolbar(total)}{items.map(renderItemCard)}</m.div>
  }

  const renderTabs = () => (
    <div className={styles.tabGroup}>
      {DISPLAY_DOMAINS.map((key) => {
        const Icon = DOMAIN_ICONS[key]
        return (
          <button key={key} type="button" className={`${styles.tabBtn} ${domain === key ? styles.tabActive : ''}`} onClick={() => setDomain(key)}>
            <Icon size={15} /> {t(`domains.${key}`)}
          </button>
        )
      })}
    </div>
  )

  const renderCapabilityTabs = () => {
    if (supportedCapabilities.length <= 1) return null
    return (
      <div className={styles.tabGroup} role="group" aria-label={t('search.capabilityMode')}>
        {supportedCapabilities.map((key) => (
          <button
            key={key}
            type="button"
            className={`${styles.tabBtn} ${capability === key ? styles.tabActive : ''}`}
            onClick={() => setCapability(key)}
            aria-pressed={capability === key}
          >
            {key === 'search' && domain === 'web' ? t('domains.web') : t(`capabilities.${key}`)}
          </button>
        ))}
      </div>
    )
  }

  const renderForm = (compact = false) => (
    <form
      className={styles.searchForm}
      onSubmit={(e) => { e.preventDefault(); if (canSearch) handleSearch() }}
      style={compact ? { maxWidth: '100%' } : undefined}
    >
      <div className={styles.searchBar}>
        <input
          ref={inputRef}
          className={styles.searchInput}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('search.placeholder')}
          aria-label={t('search.placeholder')}
          required
        />
        <button type="submit" className={styles.searchButton} disabled={!canSearch}>
          {loading ? t('search.searching') : t('search.searchBtn')}
        </button>
      </div>
    </form>
  )

  return (
    <div className={`${styles.page} ${hasResults ? styles.compact : ''}`}>
      {!hasResults && (
        <m.div className={styles.hero} {...fadeInUp}>
          <div className={styles.gridOverlay} />
          <h1 className={styles.heroTitle}>{t('app.name')}</h1>
          <p className={styles.heroSubtitle}><Cpu size={14} />{t('search.subtitle')}</p>

          {renderTabs()}
          {renderCapabilityTabs()}
          {renderForm()}
          <SearchMemoryPanel
            history={searchHistory}
            favorites={favoriteSearches}
            isCurrentFavorite={isCurrentFavorite}
            canFavorite={canFavoriteCurrentSearch}
            onApply={applySearchMemory}
            onToggleCurrentFavorite={toggleCurrentFavorite}
            onRemoveFavorite={removeFavoriteSearch}
            onClearHistory={clearCurrentSearchHistory}
            classes={memoryClasses}
          />

          <div className={styles.sourceSection}>
            <div className={styles.sourceLabel}>{t('search.dataSources')}:</div>
            <div className={styles.sourceGrid}>
              {availableSources.map((source) => {
                const isSelected = selectedSources.includes(source.name)
                return (
                  <button key={source.name} type="button" className={`${styles.sourcePill} ${isSelected ? styles.sourcePillActive : ''}`} onClick={() => toggleSource(source.name)}>
                    {source.name}
                  </button>
                )
              })}
            </div>
          </div>

          {!loading && !error && (
            <div className={styles.suggestions}>
              {SEARCH_SUGGESTIONS.map((s) => (
                <button key={s} type="button" className={styles.suggestionChip} onClick={() => setQuery(s)}>{s}</button>
              ))}
            </div>
          )}
        </m.div>
      )}

      {hasResults && (
        <div>
          {renderTabs()}
          {renderCapabilityTabs()}
          {renderForm(true)}
          <SearchMemoryPanel
            history={searchHistory}
            favorites={favoriteSearches}
            isCurrentFavorite={isCurrentFavorite}
            canFavorite={canFavoriteCurrentSearch}
            onApply={applySearchMemory}
            onToggleCurrentFavorite={toggleCurrentFavorite}
            onRemoveFavorite={removeFavoriteSearch}
            onClearHistory={clearCurrentSearchHistory}
            classes={memoryClasses}
          />
        </div>
      )}

      <div className={styles.results} aria-live="polite">{renderResults()}</div>
    </div>
  )
}
