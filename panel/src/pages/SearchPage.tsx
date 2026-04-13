import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { FileText, Shield, Globe, Users, Calendar, Link, Building } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { MultiSelect, type SelectOption } from '../components/common/MultiSelect'
import { formatError } from '../lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '../lib/normalize'
import type { SearchCategory, SourceInfo, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '../types'
import { staggerContainer, staggerItem } from '../lib/animations'
import styles from './SearchPage.module.scss'

const TABS: { key: SearchCategory; labelKey: string; icon: typeof FileText }[] = [
  { key: 'paper', labelKey: 'search.papers', icon: FileText },
  { key: 'patent', labelKey: 'search.patents', icon: Shield },
  { key: 'web', labelKey: 'search.web', icon: Globe },
]

function toSelectOptions(sources: SourceInfo[]): SelectOption[] {
  return sources.map((s) => ({
    value: s.name,
    label: s.name,
    description: s.description,
    needsKey: s.needs_key,
  }))
}

const FALLBACK_OPTIONS: Record<SearchCategory, SelectOption[]> = {
  paper: [
    { value: 'openalex', label: 'openalex', description: '开放学术图谱' },
    { value: 'arxiv', label: 'arxiv', description: '预印本' },
  ],
  patent: [
    { value: 'google_patents', label: 'google_patents', description: '实验性爬虫' },
  ],
  web: [
    { value: 'duckduckgo', label: 'duckduckgo', description: '爬虫' },
    { value: 'bing', label: 'bing', description: '爬虫' },
  ],
}

const DEFAULT_SELECTED: Record<SearchCategory, string[]> = {
  paper: ['openalex', 'arxiv'],
  patent: ['google_patents'],
  web: ['duckduckgo', 'bing'],
}

function resolveSourceOptions(category: SearchCategory, sources: SourceInfo[]): SelectOption[] {
  const options = toSelectOptions(sources)
  return options.length > 0 ? options : FALLBACK_OPTIONS[category]
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
  const [tab, setTab] = useState<SearchCategory>('paper')
  const [query, setQuery] = useState('')
  const [sourceOptions, setSourceOptions] = useState<Record<SearchCategory, SelectOption[]>>(FALLBACK_OPTIONS)
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

  useEffect(() => {
    let cancelled = false
    api.getSources().then((res) => {
      if (cancelled) return
      const nextOptions = {
        paper: resolveSourceOptions('paper', res.paper),
        patent: resolveSourceOptions('patent', res.patent),
        web: resolveSourceOptions('web', res.web),
      }
      setSourceOptions(nextOptions)
      setSelections((prev) => sanitizeSelections(prev, nextOptions))
    }).catch((err) => { console.warn('[SouWen] Failed to load sources from API, using fallback:', err) })
    return () => { cancelled = true }
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

  const renderPaperCard = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    const key = p.doi || `paper-${p.source}-${i}`
    return (
      <m.div key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.resultTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}</a>
          ) : (
            p.title || t('search.untitled')
          )}
        </div>
        <div className={styles.resultMeta}>
          {p.authors.length > 0 && (
            <span><Users size={14} /> {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? t('search.andMore') : ''}</span>
          )}
          {p.year && <span><Calendar size={14} /> {p.year}</span>}
          {p.doi && <span><Link size={14} /> {p.doi}</span>}
          {p.source && <span className={styles.sourceTag}>{p.source}</span>}
        </div>
        {p.abstract && (
          <div className={styles.resultAbstract}>
            {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
          </div>
        )}
      </m.div>
    )
  }

  const renderPatentCard = (raw: PatentResult, i: number) => {
    const p = normalizePatent(raw)
    const key = p.patentNumber || `patent-${p.source}-${i}`
    return (
      <m.div key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.resultTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}</a>
          ) : (
            p.title || t('search.untitled')
          )}
        </div>
        <div className={styles.resultMeta}>
          {p.patentNumber && (
            <span><FileText size={14} /> {p.patentNumber}</span>
          )}
          {p.applicant && (
            <span><Building size={14} /> {p.applicant}</span>
          )}
          {p.publicationDate && <span><Calendar size={14} /> {p.publicationDate}</span>}
          {p.source && <span className={styles.sourceTag}>{p.source}</span>}
        </div>
        {p.abstract && (
          <div className={styles.resultAbstract}>
            {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
          </div>
        )}
      </m.div>
    )
  }

  const renderWebCard = (raw: WebResult, i: number) => {
    const item = normalizeWeb(raw)
    const key = item.url || `web-${item.source}-${i}`
    return (
      <m.div key={key} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.resultTitle}>
          {item.url ? (
            <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
          ) : (
            item.title
          )}
        </div>
        {item.url && <div className={styles.resultUrl}>{item.url}</div>}
        {item.snippet && <div className={styles.resultAbstract}>{item.snippet}</div>}
        {(item.source || raw.engine) && <span className={styles.sourceTag}>{item.source || raw.engine}</span>}
      </m.div>
    )
  }

  const renderResults = () => {
    if (isSearchingCurrentTab) {
      return (
        <div role="status" aria-live="polite" aria-busy="true">
          <span className="srOnly">{t('search.searching', 'Searching')}</span>
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

    return <EmptyState type="search" title={t('search.startSearch')} description={t('search.placeholder')} />
  }

  return (
    <div className={styles.page}>
      <div className={styles.tabs}>
        {TABS.map((tabItem) => (
          <button
            key={tabItem.key}
            className={`${styles.tab} ${tab === tabItem.key ? styles.active : ''}`}
            onClick={() => handleTabChange(tabItem.key)}
          >
            <tabItem.icon size={16} />
            {t(tabItem.labelKey)}
          </button>
        ))}
      </div>

      <form className={styles.form} onSubmit={handleSearch} aria-busy={isSearchingCurrentTab}>
        <div className={styles.formRow}>
          <input
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('search.placeholder')}
            required
          />
          <select
            className={styles.select}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {t('search.items', { count: n })}
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary" disabled={!canSearch}>
            {isSearchingCurrentTab ? t('search.searching') : t('search.button')}
          </button>
        </div>
        <div className={styles.sourceRow}>
          <MultiSelect
            options={sourceOptions[tab]}
            selected={currentSources}
            onChange={handleSelectionChange}
            placeholder={tab === 'web' ? t('search.engines') : t('search.sources')}
          />
        </div>
      </form>

      <div className={styles.results} aria-live="polite">
        {renderResults()}
      </div>
    </div>
  )
}
