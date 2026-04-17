/**
 * 文件用途：iOS 皮肤的搜索页面，支持跨多个数据源的统一搜索
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  FileText, Users, Calendar, Link, Building,
  ExternalLink, Search,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '@core/lib/normalize'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import type {
  SearchCategory, SourceInfo, SearchResponse, WebSearchResponse,
  WebResult, PaperResult, PatentResult,
} from '@core/types'
import styles from './SearchPage.module.scss'

interface SourceOption {
  value: string
  label: string
  description?: string
}

function toSourceOptions(sources: SourceInfo[]): SourceOption[] {
  return sources.map((s) => ({ value: s.name, label: s.name, description: s.description }))
}

function makeFallbackOptions(t: (key: string) => string): Record<SearchCategory, SourceOption[]> {
  return {
    paper: [
      { value: 'openalex', label: 'openalex', description: t('search.source_openalex') },
      { value: 'arxiv', label: 'arxiv', description: t('search.source_arxiv') },
    ],
    patent: [
      { value: 'google_patents', label: 'google_patents', description: t('search.source_google_patents') },
    ],
    web: [
      { value: 'duckduckgo', label: 'duckduckgo', description: t('search.source_duckduckgo') },
      { value: 'bing', label: 'bing', description: t('search.source_bing') },
    ],
  }
}

const DEFAULT_SELECTED: Record<SearchCategory, string[]> = {
  paper: ['openalex', 'arxiv'],
  patent: ['google_patents'],
  web: ['duckduckgo', 'bing'],
}

const SEARCH_SUGGESTIONS = [
  'Large Language Model',
  'Quantum Computing',
  'CRISPR Gene Editing',
  'Transformer Architecture',
  'Climate Change',
  'Neural Radiance Fields',
]

function resolveSourceOptions(
  category: SearchCategory,
  sources: SourceInfo[],
  fallback: Record<SearchCategory, SourceOption[]>,
): SourceOption[] {
  const options = toSourceOptions(sources)
  return options.length > 0 ? options : fallback[category]
}

function sanitizeSelections(
  current: Record<SearchCategory, string[]>,
  options: Record<SearchCategory, SourceOption[]>,
): Record<SearchCategory, string[]> {
  return (Object.keys(options) as SearchCategory[]).reduce(
    (next, category) => {
      const allowed = new Set(options[category].map((o) => o.value))
      const selected = current[category].filter((v) => allowed.has(v))
      next[category] = selected.length > 0
        ? selected
        : DEFAULT_SELECTED[category].filter((v) => allowed.has(v))
      return next
    },
    { paper: [], patent: [], web: [] } as Record<SearchCategory, string[]>,
  )
}

type SearchState =
  | { status: 'idle'; tab: null; message: null }
  | { status: 'loading'; tab: SearchCategory; message: null }
  | { status: 'error'; tab: SearchCategory; message: string }

export function SearchPage() {
  const { t } = useTranslation()
  const fallbackOptions = makeFallbackOptions(t)
  const [tab, setTab] = useState<SearchCategory>('paper')
  const [query, setQuery] = useState('')
  const [sourceOptions, setSourceOptions] = useState<Record<SearchCategory, SourceOption[]>>(fallbackOptions)
  const [selections, setSelections] = useState<Record<SearchCategory, string[]>>({ ...DEFAULT_SELECTED })
  const [count] = useState(10)
  const [searchState, setSearchState] = useState<SearchState>({ status: 'idle', tab: null, message: null })
  const [paperResults, setPaperResults] = useState<SearchResponse | null>(null)
  const [patentResults, setPatentResults] = useState<SearchResponse | null>(null)
  const [webResults, setWebResults] = useState<WebSearchResponse | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)
  const activeRequestRef = useRef<{ id: number; controller: AbortController } | null>(null)
  const requestIdRef = useRef(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    api.getSources().then((res) => {
      if (cancelled) return
      const nextOptions = {
        paper: resolveSourceOptions('paper', res.paper, fallbackOptions),
        patent: resolveSourceOptions('patent', res.patent, fallbackOptions),
        web: resolveSourceOptions('web', res.web, fallbackOptions),
      }
      setSourceOptions(nextOptions)
      setSelections((prev) => sanitizeSelections(prev, nextOptions))
    }).catch((err) => { console.warn('[SouWen] Failed to load sources:', err) })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    return () => { activeRequestRef.current?.controller.abort() }
  }, [])

  const toggleSource = useCallback((name: string) => {
    setSelections((prev) => {
      const curr = prev[tab]
      const next = curr.includes(name) ? curr.filter((s) => s !== name) : [...curr, name]
      return { ...prev, [tab]: next }
    })
  }, [tab])

  const currentSources = selections[tab]
  const canSearch = query.trim().length > 0 && currentSources.length > 0
  const isSearchingCurrentTab = searchState.status === 'loading' && searchState.tab === tab

  const handleSearch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!canSearch) return
      const requestId = requestIdRef.current + 1
      requestIdRef.current = requestId
      activeRequestRef.current?.controller.abort()
      const controller = new AbortController()
      activeRequestRef.current = { id: requestId, controller }
      setSearchState({ status: 'loading', tab, message: null })
      const joined = currentSources.join(',')
      try {
        if (tab === 'paper') {
          setPaperResults(null)
          const res = await api.searchPaper(query, joined, count, controller.signal)
          if (activeRequestRef.current?.id !== requestId) return
          setPaperResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total }))
        } else if (tab === 'patent') {
          setPatentResults(null)
          const res = await api.searchPatent(query, joined, count, controller.signal)
          if (activeRequestRef.current?.id !== requestId) return
          setPatentResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total }))
        } else {
          setWebResults(null)
          const res = await api.searchWeb(query, joined, count, controller.signal)
          if (activeRequestRef.current?.id !== requestId) return
          setWebResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total_results }))
        }
      } catch (err) {
        if (controller.signal.aborted || activeRequestRef.current?.id !== requestId) return
        const message = formatError(err)
        setSearchState({ status: 'error', tab, message })
        addToast('error', t('search.failed', { message }))
      } finally {
        if (activeRequestRef.current?.id === requestId) {
          activeRequestRef.current = null
        }
      }
    },
    [tab, query, currentSources, canSearch, count, addToast, t],
  )

  const handleRetry = useCallback(() => {
    const syntheticEvent = { preventDefault: () => {} } as FormEvent
    handleSearch(syntheticEvent)
  }, [handleSearch])

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
        {item.url && <div className={styles.resultUrl}>{item.url}</div>}
        {item.snippet && <p className={styles.resultAbstract}>{item.snippet}</p>}
      </m.article>
    )
  }

  const hasResults =
    (tab === 'paper' && paperResults) ||
    (tab === 'patent' && patentResults) ||
    (tab === 'web' && webResults)

  const renderResults = () => {
    if (isSearchingCurrentTab) {
      return (
        <div role="status" aria-live="polite" aria-busy="true">
          <div className={styles.searchingHint}>{t('search.searchingHint')}</div>
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className={styles.skeletonCard} />
          ))}
        </div>
      )
    }

    if (searchState.status === 'error' && searchState.tab === tab) {
      return (
        <div className={styles.errorState}>
          <p>{searchState.message}</p>
          <button type="button" className={styles.retryBtn} onClick={handleRetry}>
            {t('search.retrySearch')}
          </button>
        </div>
      )
    }

    if (tab === 'paper' && paperResults) {
      const allItems = paperResults.results.flatMap((r) => r.results) as PaperResult[]
      if (allItems.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: paperResults.total })}</div>
          {allItems.map((item, i) => renderPaperCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'patent' && patentResults) {
      const allItems = patentResults.results.flatMap((r) => r.results) as PatentResult[]
      if (allItems.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: patentResults.total })}</div>
          {allItems.map((item, i) => renderPatentCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'web' && webResults) {
      if (webResults.results.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: webResults.total_results })}</div>
          {webResults.results.map((item, i) => renderWebCard(item, i))}
        </m.div>
      )
    }

    return null
  }

  const TAB_LABELS: Record<SearchCategory, string> = {
    paper: t('search.papers'),
    patent: t('search.patents'),
    web: t('search.web'),
  }

  return (
    <div className={`${styles.page} ${hasResults ? styles.compact : ''}`}>
      {/* ── Hero (no results) ── */}
      {!hasResults && (
        <m.div className={styles.hero} {...fadeInUp}>
          <h1 className={styles.heroTitle}>SouWen</h1>
          <p className={styles.heroSubtitle}>
            {t('search.heroSubtitle', 'Search across papers, patents, and the web.')}
          </p>

          {/* Tabs */}
          <div className={styles.tabGroup}>
            {(['paper', 'patent', 'web'] as SearchCategory[]).map((key) => (
              <button
                key={key}
                type="button"
                className={`${styles.tabBtn} ${tab === key ? styles.tabActive : ''}`}
                onClick={() => setTab(key)}
              >
                {TAB_LABELS[key]}
              </button>
            ))}
          </div>

          {/* Search */}
          <form className={styles.searchForm} onSubmit={handleSearch}>
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
              <button
                type="submit"
                className={styles.searchButton}
                disabled={!canSearch}
              >
                {isSearchingCurrentTab ? t('search.searching') : t('search.searchBtn', 'Search')}
              </button>
            </div>
          </form>

          {/* Source toggles */}
          <div className={styles.sourceSection}>
            <div className={styles.sourceLabel}>{t('search.dataSources', 'Data Sources')}</div>
            <div className={styles.sourceGrid}>
              {sourceOptions[tab].map((source) => {
                const isSelected = currentSources.includes(source.value)
                return (
                  <button
                    key={source.value}
                    type="button"
                    className={`${styles.sourcePill} ${isSelected ? styles.sourcePillActive : ''}`}
                    onClick={() => toggleSource(source.value)}
                  >
                    {source.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Suggestions */}
          {searchState.status === 'idle' && (
            <div className={styles.suggestions}>
              {SEARCH_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={styles.suggestionChip}
                  onClick={() => setQuery(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </m.div>
      )}

      {/* ── Compact search bar (when results exist) ── */}
      {hasResults && (
        <div>
          <div className={styles.tabGroup}>
            {(['paper', 'patent', 'web'] as SearchCategory[]).map((key) => (
              <button
                key={key}
                type="button"
                className={`${styles.tabBtn} ${tab === key ? styles.tabActive : ''}`}
                onClick={() => setTab(key)}
              >
                {TAB_LABELS[key]}
              </button>
            ))}
          </div>
          <form className={styles.searchForm} onSubmit={handleSearch} style={{ maxWidth: '100%' }}>
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
              <button
                type="submit"
                className={styles.searchButton}
                disabled={!canSearch}
              >
                {isSearchingCurrentTab ? t('search.searching') : t('search.searchBtn', 'Search')}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Results ── */}
      <div className={styles.results} aria-live="polite">
        {renderResults()}
      </div>
    </div>
  )
}
