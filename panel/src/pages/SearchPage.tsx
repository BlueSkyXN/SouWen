import { useState, useCallback, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { FileText, Shield, Globe, Users, Calendar, Link, Building } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Spinner } from '../components/common/Spinner'
import { formatError } from '../lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '../lib/normalize'
import type { SearchCategory, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '../types'
import styles from './SearchPage.module.scss'

const TABS: { key: SearchCategory; labelKey: string; icon: typeof FileText }[] = [
  { key: 'paper', labelKey: 'search.papers', icon: FileText },
  { key: 'patent', labelKey: 'search.patents', icon: Shield },
  { key: 'web', labelKey: 'search.web', icon: Globe },
]

const DEFAULT_SOURCES: Record<SearchCategory, string> = {
  paper: 'openalex,arxiv',
  patent: 'patentsview,pqai',
  web: 'duckduckgo,yahoo,brave',
}

const staggerContainer = {
  animate: { transition: { staggerChildren: 0.05 } },
}
const staggerItem = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
}

export function SearchPage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<SearchCategory>('paper')
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState(DEFAULT_SOURCES.paper)
  const [count, setCount] = useState(10)
  const [loading, setLoading] = useState(false)
  const [paperResults, setPaperResults] = useState<SearchResponse | null>(null)
  const [patentResults, setPatentResults] = useState<SearchResponse | null>(null)
  const [webResults, setWebResults] = useState<WebSearchResponse | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)

  const handleTabChange = useCallback(
    (key: SearchCategory) => {
      setTab(key)
      setSources(DEFAULT_SOURCES[key])
    },
    [],
  )

  const handleSearch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!query.trim()) return
      setLoading(true)
      try {
        if (tab === 'paper') {
          const res = await api.searchPaper(query, sources, count)
          setPaperResults(res)
          addToast('success', t('search.success', { count: res.total }))
        } else if (tab === 'patent') {
          const res = await api.searchPatent(query, sources, count)
          setPatentResults(res)
          addToast('success', t('search.success', { count: res.total }))
        } else {
          const res = await api.searchWeb(query, sources, count)
          setWebResults(res)
          addToast('success', t('search.success', { count: res.total }))
        }
      } catch (err) {
        addToast('error', t('search.failed', { message: formatError(err) }))
      } finally {
        setLoading(false)
      }
    },
    [tab, query, sources, count, addToast, t],
  )

  const renderPaperCard = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    return (
      <m.div key={i} className={styles.resultCard} variants={staggerItem}>
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
    return (
      <m.div key={i} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.resultTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || t('search.untitled')}</a>
          ) : (
            p.title || t('search.untitled')
          )}
        </div>
        <div className={styles.resultMeta}>
          {(p.patentNumber || raw.patent_number) && (
            <span><FileText size={14} /> {p.patentNumber || raw.patent_number}</span>
          )}
          {(p.applicant || raw.assignee) && (
            <span><Building size={14} /> {p.applicant || raw.assignee}</span>
          )}
          {raw.date && <span><Calendar size={14} /> {raw.date}</span>}
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
    return (
      <m.div key={i} className={styles.resultCard} variants={staggerItem}>
        <div className={styles.resultTitle}>
          <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
        </div>
        <div className={styles.resultUrl}>{item.url}</div>
        {item.snippet && <div className={styles.resultAbstract}>{item.snippet}</div>}
        {(item.source || raw.engine) && <span className={styles.sourceTag}>{item.source || raw.engine}</span>}
      </m.div>
    )
  }

  const renderResults = () => {
    if (loading) return <Spinner size="lg" label={t('search.searching')} />

    if (tab === 'paper' && paperResults) {
      const allItems = paperResults.results.flatMap((r) => r.results) as PaperResult[]
      if (allItems.length === 0) return <div className={styles.empty}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: paperResults.total })}</div>
          {allItems.map((item, i) => renderPaperCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'patent' && patentResults) {
      const allItems = patentResults.results.flatMap((r) => r.results) as PatentResult[]
      if (allItems.length === 0) return <div className={styles.empty}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: patentResults.total })}</div>
          {allItems.map((item, i) => renderPatentCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'web' && webResults) {
      if (webResults.results.length === 0) return <div className={styles.empty}>{t('search.noResults')}</div>
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          <div className={styles.resultCount}>{t('search.resultCount', { count: webResults.total })}</div>
          {webResults.results.map((item, i) => renderWebCard(item, i))}
        </m.div>
      )
    }

    return <div className={styles.empty}>{t('search.startSearch')}</div>
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

      <form className={styles.form} onSubmit={handleSearch}>
        <div className={styles.formRow}>
          <input
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('search.placeholder')}
            required
          />
          <input
            className={styles.inputSm}
            type="text"
            value={sources}
            onChange={(e) => setSources(e.target.value)}
            placeholder={tab === 'web' ? t('search.engines') : t('search.sources')}
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
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? t('search.searching') : t('search.button')}
          </button>
        </div>
      </form>

      <div className={styles.results}>{renderResults()}</div>
    </div>
  )
}
