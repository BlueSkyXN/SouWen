import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { FileText, Shield, Globe, Users, Calendar, Link, Building, Search, ExternalLink, Sparkles } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { MultiSelect, type SelectOption } from '../components/common/MultiSelect'
import { SegmentedControl } from '../components/common/SegmentedControl'
import { Badge } from '../components/common/Badge'
import { formatError } from '../lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '../lib/normalize'
import type { SearchCategory, SourceInfo, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '../types'
import { staggerContainer, staggerItem, fadeInUp } from '../lib/animations'
import styles from './SearchPage.module.scss'

const TAB_OPTIONS: { value: SearchCategory; label: string; icon: React.ReactNode }[] = [
  { value: 'paper', label: '', icon: <FileText size={15} /> },
  { value: 'patent', label: '', icon: <Shield size={15} /> },
  { value: 'web', label: '', icon: <Globe size={15} /> },
]

function toSelectOptions(sources: SourceInfo[]): SelectOption[] {
  return sources.map((s) => ({
    value: s.name,
    label: s.name,
    description: s.description,
    needsKey: s.needs_key,
  }))
}

function makeFallbackOptions(t: (key: string) => string): Record<SearchCategory, SelectOption[]> {
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
  fallback: Record<SearchCategory, SelectOption[]>,
): SelectOption[] {
  const options = toSelectOptions(sources)
  return options.length > 0 ? options : fallback[category]
}

function sanitizeSelections(
  current: Record<SearchCategory, string[]>,
  options: Record<SearchCategory, SelectOption[]>,
): Record<SearchCategory, string[]> {
  return (Object.keys(options) as SearchCategory[]).reduce(
    (next, category) => {
      const allowed = new Set(options[category].map((option) => option.value))
      const selected = current[category].filter((value) => allowed.has(value))
      if (selected.length > 0) {
        next[category] = selected
        return next
      }

      next[category] = DEFAULT_SELECTED[category].filter((value) => allowed.has(value))
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
  const [sourceOptions, setSourceOptions] = useState<Record<SearchCategory, SelectOption[]>>(fallbackOptions)
  const [selections, setSelections] = useState<Record<SearchCategory, string[]>>({
    ...DEFAULT_SELECTED,
  })
  const [count, setCount] = useState(10)
  const [searchState, setSearchState] = useState<SearchState>({ status: 'idle', tab: null, message: null })
  const [paperResults, setPaperResults] = useState<SearchResponse | null>(null)
  const [patentResults, setPatentResults] = useState<SearchResponse | null>(null)
  const [webResults, setWebResults] = useState<WebSearchResponse | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)
  const activeRequestRef = useRef<{ id: number; controller: AbortController } | null>(null)
  const requestIdRef = useRef(0)

  const segmentOptions = TAB_OPTIONS.map((o) => ({
    ...o,
    label: t(`search.${o.value === 'paper' ? 'papers' : o.value === 'patent' ? 'patents' : 'web'}`),
  }))

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
    }).catch((err) => { console.warn('[SouWen] Failed to load sources from API, using fallback:', err) })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    return () => {
      activeRequestRef.current?.controller.abort()
    }
  }, [])

  const handleTabChange = useCallback((key: SearchCategory) => {
    setTab(key)
  }, [])

  const handleSelectionChange = useCallback(
    (selected: string[]) => {
      setSelections((prev) => ({ ...prev, [tab]: selected }))
    },
    [tab],
  )

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
                <ExternalLink size={14} className={styles.externalIcon} />
              </a>
            ) : (
              p.title || t('search.untitled')
            )}
          </h3>
          {p.source && <Badge color="blue">{p.source}</Badge>}
        </div>
        <div className={styles.resultMeta}>
          {p.authors.length > 0 && (
            <span><Users size={14} /> {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? t('search.andMore') : ''}</span>
          )}
          {p.year && <span><Calendar size={14} /> {p.year}</span>}
          {p.doi && <span><Link size={14} /> {p.doi}</span>}
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
                <ExternalLink size={14} className={styles.externalIcon} />
              </a>
            ) : (
              p.title || t('search.untitled')
            )}
          </h3>
          {p.source && <Badge color="indigo">{p.source}</Badge>}
        </div>
        <div className={styles.resultMeta}>
          {p.patentNumber && (
            <span><FileText size={14} /> {p.patentNumber}</span>
          )}
          {p.applicant && (
            <span><Building size={14} /> {p.applicant}</span>
          )}
          {p.publicationDate && <span><Calendar size={14} /> {p.publicationDate}</span>}
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
                <ExternalLink size={14} className={styles.externalIcon} />
              </a>
            ) : (
              item.title
            )}
          </h3>
          {(item.source || raw.engine) && <Badge color="teal">{item.source || raw.engine}</Badge>}
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
          <ResultsSkeleton count={4} />
        </div>
      )
    }

    if (searchState.status === 'error' && searchState.tab === tab) {
      return (
        <EmptyState
          type="error"
          title={t('search.errorStateTitle')}
          description={searchState.message}
          action={
            <button type="button" className="btn btn-primary btn-sm" onClick={handleRetry}>
              {t('search.retrySearch')}
            </button>
          }
        />
      )
    }

    if (tab === 'paper' && paperResults) {
      const allItems = paperResults.results.flatMap((r) => r.results) as PaperResult[]
      if (allItems.length === 0) return <EmptyState type="search" title={t('search.noResults')} />
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: paperResults.total })}</div>
          {allItems.map((item, i) => renderPaperCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'patent' && patentResults) {
      const allItems = patentResults.results.flatMap((r) => r.results) as PatentResult[]
      if (allItems.length === 0) return <EmptyState type="search" title={t('search.noResults')} />
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: patentResults.total })}</div>
          {allItems.map((item, i) => renderPatentCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'web' && webResults) {
      if (webResults.results.length === 0) return <EmptyState type="search" title={t('search.noResults')} />
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: webResults.total_results })}</div>
          {webResults.results.map((item, i) => renderWebCard(item, i))}
        </m.div>
      )
    }

    return (
      <div className={styles.emptyStateCustom}>
        <div className={styles.emptyGlow}>
          <div className={styles.emptyGlowOrb} />
          <div className={styles.emptyGlowOrb} />
          <div className={styles.emptyGlowOrb} />
          <div className={styles.emptyIconWrap}>
            <Search size={36} strokeWidth={1.5} />
          </div>
        </div>
        <div className={styles.emptyTitle}>{t('search.enterKeyword')}</div>
        <div className={styles.emptyDesc}>{t('search.startSearchDesc')}</div>
        <div className={styles.emptySuggestions}>
          {SEARCH_SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              className={styles.suggestionChip}
              onClick={() => { setQuery(s) }}
            >
              <Sparkles size={13} />
              {s}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={`${styles.heroSection} ${hasResults ? styles.hasResults : ''}`}>
        {/* Tab Switcher */}
        <div className={styles.tabBar}>
          <SegmentedControl options={segmentOptions} value={tab} onChange={handleTabChange} />
        </div>

        {/* Hero Search Bar */}
        <m.form
          className={styles.searchForm}
          onSubmit={handleSearch}
          aria-busy={isSearchingCurrentTab}
          {...fadeInUp}
        >
          <div className={styles.searchBarWrap}>
            <div className={styles.searchBar}>
              <Search size={22} className={styles.searchIcon} />
              <input
                className={styles.searchInput}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('search.placeholder')}
                required
              />
              <select
                className={styles.countSelect}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                aria-label={t('search.items', { count })}
              >
                {[5, 10, 20, 50].map((n) => (
                  <option key={n} value={n}>
                    {t('search.items', { count: n })}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className={styles.searchButton}
                disabled={!canSearch}
                aria-label={t('search.button')}
              >
                {isSearchingCurrentTab ? t('search.searching') : t('search.button')}
              </button>
            </div>
          </div>

          {/* Source Selector */}
          <div className={styles.sourceRow}>
            <span className={styles.sourceLabel}>{t('search.searchScope')}</span>
            <div className={styles.sourceSelect}>
              <MultiSelect
                options={sourceOptions[tab]}
                selected={currentSources}
                onChange={handleSelectionChange}
                placeholder={tab === 'web' ? t('search.engines') : t('search.sources')}
              />
            </div>
          </div>
        </m.form>

        {/* Results */}
        <div className={styles.results} aria-live="polite" style={{ width: '100%' }}>
          {renderResults()}
        </div>
      </div>
    </div>
  )
}
