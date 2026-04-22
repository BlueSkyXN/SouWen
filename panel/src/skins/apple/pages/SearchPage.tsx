/**
 * 文件用途：Apple 皮肤的搜索页面（v1 单 domain 版）。
 *
 * 设计要点：
 *   - 路由 /search/:domain 决定本页搜索域；本组件维护 `domain` 局部状态以支持顶部 tab 切换。
 *   - 搜索状态由 `useSearchPage` 集中管理（query / sources / capability / loading / error）。
 *   - paper / patent 走 SearchResponse（嵌套），其他 domain 一律走 WebSearchResponse（扁平）。
 */

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  FileText, Users, Calendar, Link, Building,
  ExternalLink, Search,
  List, LayoutGrid, Grid3X3, Download, Globe,
  Shield, BookOpen, Zap, MessageCircle, Code2, Play,
} from 'lucide-react'
import { useNotificationStore } from '@core/stores/notificationStore'
import { normalizePaper, normalizePatent, normalizeWeb } from '@core/lib/normalize'
import { extractDomain } from '@core/lib/url'
import { exportPapers, exportPatents, exportWebResults, type ExportFormat } from '@core/lib/export'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import { useSearchPage, type Domain } from '@core/hooks/useSearchPage'
import type {
  SearchResponse, WebSearchResponse,
  WebResult, PaperResult, PatentResult,
} from '@core/types'
import styles from './SearchPage.module.scss'

type LayoutMode = 'list' | 'card' | 'grid'

const DISPLAY_DOMAINS: Domain[] = [
  'paper', 'patent', 'web', 'cn_tech', 'social', 'developer', 'knowledge', 'video',
]

const DOMAIN_ICONS: Record<Domain, typeof FileText> = {
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

function flattenItems(domain: Domain, responses: Array<SearchResponse | WebSearchResponse>): unknown[] {
  if (domain === 'paper' || domain === 'patent') {
    return (responses as SearchResponse[]).flatMap((r) => r.results.flatMap((s) => s.results))
  }
  return (responses as WebSearchResponse[]).flatMap((r) => r.results)
}

function totalCountOf(domain: Domain, responses: Array<SearchResponse | WebSearchResponse>): number {
  if (domain === 'paper' || domain === 'patent') {
    return (responses as SearchResponse[]).reduce((sum, r) => sum + (r.total ?? 0), 0)
  }
  return (responses as WebSearchResponse[]).reduce((sum, r) => sum + (r.total_results ?? 0), 0)
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
    responses, loading, error,
    availableSources, selectedSources, toggleSource,
    handleSearch,
  } = useSearchPage(domain)

  const addToast = useNotificationStore((s) => s.addToast)
  const SEARCH_SUGGESTIONS = [
    t('search.suggestion1', '大语言模型'),
    t('search.suggestion2', '量子计算'),
    t('search.suggestion3', 'CRISPR 基因编辑'),
    t('search.suggestion4', 'Transformer 架构'),
    t('search.suggestion5', '气候变化'),
    t('search.suggestion6', '神经辐射场'),
  ]

  // Sync URL changes back to local state
  useEffect(() => {
    if (urlDomain && DISPLAY_DOMAINS.includes(urlDomain as Domain) && urlDomain !== domain) {
      setDomain(urlDomain as Domain)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlDomain])

  // Toast on search completion / error
  const prevLoadingRef = useRef(false)
  useEffect(() => {
    if (prevLoadingRef.current && !loading) {
      if (error) {
        addToast('error', t('search.failed', { message: error.message }))
      } else if (responses.length > 0) {
        addToast('success', t('search.success', { count: totalCountOf(domain, responses) }))
      }
    }
    prevLoadingRef.current = loading
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading])

  const canSearch = query.trim().length > 0 && selectedSources.length > 0
  const items = flattenItems(domain, responses)
  const hasResults = responses.length > 0

  const renderPaperCard = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    const key = p.doi || `paper-${p.source}-${i}`
    return (
      <m.article key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.cardHeader}>
          <h3 className={styles.resultTitle}>
            {p.url ? (
              <a href={p.url} target="_blank" rel="noopener noreferrer">
                {p.title || t('search.untitled')}
                <ExternalLink size={12} className={styles.externalIcon} />
              </a>
            ) : (p.title || t('search.untitled'))}
          </h3>
          {p.source && <span className={styles.sourceBadge}>{p.source}</span>}
        </div>
        <div className={styles.resultMeta}>
          {p.authors.length > 0 && (
            <span><Users size={12} /> {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? t('search.andMore') : ''}</span>
          )}
          {p.year && <span><Calendar size={12} /> {p.year}</span>}
          {p.doi && <span><Link size={12} /> {p.doi}</span>}
        </div>
        {p.abstract && (
          <p className={styles.resultAbstract}>
            {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
          </p>
        )}
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
            {p.url ? (
              <a href={p.url} target="_blank" rel="noopener noreferrer">
                {p.title || t('search.untitled')}
                <ExternalLink size={12} className={styles.externalIcon} />
              </a>
            ) : (p.title || t('search.untitled'))}
          </h3>
          {p.source && <span className={styles.sourceBadge}>{p.source}</span>}
        </div>
        <div className={styles.resultMeta}>
          {p.patentNumber && <span><FileText size={12} /> {p.patentNumber}</span>}
          {p.applicant && <span><Building size={12} /> {p.applicant}</span>}
          {p.publicationDate && <span><Calendar size={12} /> {p.publicationDate}</span>}
        </div>
        {p.abstract && (
          <p className={styles.resultAbstract}>
            {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
          </p>
        )}
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
            {item.url ? (
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.title}
                <ExternalLink size={12} className={styles.externalIcon} />
              </a>
            ) : item.title}
          </h3>
          {(item.source || raw.engine) && <span className={styles.sourceBadge}>{item.source || raw.engine}</span>}
        </div>
        {item.url && (
          <div className={styles.resultUrl} title={item.url}>
            <Globe size={12} /> {dom}
          </div>
        )}
        {item.snippet && <p className={styles.resultAbstract}>{item.snippet}</p>}
      </m.article>
    )
  }

  const renderItemCard = (item: unknown, i: number) => {
    if (domain === 'paper') return renderPaperCard(item as PaperResult, i)
    if (domain === 'patent') return renderPatentCard(item as PatentResult, i)
    return renderWebCard(item as WebResult, i)
  }

  const renderItemListItem = (item: unknown, i: number) => {
    // Compact list rendering — adapt minimal info for each domain
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
    let title = ''
    let url = ''
    let source = ''
    let abstract = ''
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
    if (domain === 'paper') {
      const list = (items as PaperResult[]).map(normalizePaper)
      exportedCount = list.length
      exportPapers(list, format)
    } else if (domain === 'patent') {
      const list = (items as PatentResult[]).map(normalizePatent)
      exportedCount = list.length
      exportPatents(list, format)
    } else {
      const list = (items as WebResult[]).map(normalizeWeb)
      exportedCount = list.length
      exportWebResults(list, format)
    }
    if (exportedCount > 0) addToast('success', t('search.exported', { count: exportedCount }))
  }

  const renderToolbar = (totalCount: number) => (
    <div className={styles.resultsToolbar}>
      <div className={styles.resultCount}>{t('search.resultCount', { count: totalCount })}</div>
      <div className={styles.toolbarActions}>
        <div className={styles.layoutToggle} role="group" aria-label={t('search.layoutCard')}>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'list' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('list')} aria-label={t('search.layoutList')} title={t('search.layoutList')}><List size={14} /></button>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'card' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('card')} aria-label={t('search.layoutCard')} title={t('search.layoutCard')}><LayoutGrid size={14} /></button>
          <button type="button" className={`${styles.layoutBtn} ${layoutMode === 'grid' ? styles.layoutBtnActive : ''}`} onClick={() => setLayoutMode('grid')} aria-label={t('search.layoutGrid')} title={t('search.layoutGrid')}><Grid3X3 size={14} /></button>
        </div>
        <div className={styles.exportGroup} role="group" aria-label={t('search.exportTitle')}>
          <button type="button" className={styles.exportBtn} onClick={() => handleExport('csv')} title={t('search.exportCSV')}><Download size={13} /> {t('search.exportCSV')}</button>
          <button type="button" className={styles.exportBtn} onClick={() => handleExport('xls')} title={t('search.exportXLS')}><Download size={13} /> {t('search.exportXLS')}</button>
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
      return (
        <div>
          {renderToolbar(total)}
          <div className={styles.resultList}>{items.map(renderItemListItem)}</div>
        </div>
      )
    }
    if (layoutMode === 'grid') {
      return (
        <div>
          {renderToolbar(total)}
          <m.div className={styles.resultGrid} variants={staggerContainer} initial="initial" animate="animate">
            {items.map(renderItemGridCard)}
          </m.div>
        </div>
      )
    }
    return (
      <m.div variants={staggerContainer} initial="initial" animate="animate">
        {renderToolbar(total)}
        {items.map(renderItemCard)}
      </m.div>
    )
  }

  const renderTabs = () => (
    <div className={styles.tabGroup}>
      {DISPLAY_DOMAINS.map((key) => {
        const Icon = DOMAIN_ICONS[key]
        return (
          <button
            key={key}
            type="button"
            className={`${styles.tabBtn} ${domain === key ? styles.tabActive : ''}`}
            onClick={() => setDomain(key)}
          >
            <Icon size={14} /> {t(`domains.${key}`)}
          </button>
        )
      })}
    </div>
  )

  const renderForm = (compact = false) => (
    <form
      className={styles.searchForm}
      onSubmit={(e) => { e.preventDefault(); if (canSearch) handleSearch() }}
      style={compact ? { maxWidth: '100%' } : undefined}
    >
      <div className={styles.searchBar}>
        <Search size={18} className={styles.searchIcon} />
        <input
          ref={inputRef}
          className={styles.searchInput}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('search.placeholder')}
          required
        />
        <button type="submit" className={styles.searchButton} disabled={!canSearch}>
          {loading ? t('search.searching') : t('search.searchBtn', 'Search')}
        </button>
      </div>
    </form>
  )

  return (
    <div className={`${styles.page} ${hasResults ? styles.compact : ''}`}>
      {!hasResults && (
        <m.div className={styles.hero} {...fadeInUp}>
          <h1 className={styles.heroTitle}>SouWen</h1>
          <p className={styles.heroSubtitle}>
            {t('search.heroSubtitle', 'Search across papers, patents, and the web.')}
          </p>

          {renderTabs()}
          {renderForm()}

          <div className={styles.sourceSection}>
            <div className={styles.sourceLabel}>{t('search.dataSources', 'Data Sources')}</div>
            <div className={styles.sourceGrid}>
              {availableSources.map((source) => {
                const isSelected = selectedSources.includes(source.name)
                return (
                  <button
                    key={source.name}
                    type="button"
                    className={`${styles.sourcePill} ${isSelected ? styles.sourcePillActive : ''}`}
                    onClick={() => toggleSource(source.name)}
                  >
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
          {renderForm(true)}
        </div>
      )}

      <div className={styles.results} aria-live="polite">{renderResults()}</div>
    </div>
  )
}
