import { useState, useCallback, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { FileText, Shield, Globe, Users, Calendar, Link, Building } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Spinner } from '../components/common/Spinner'
import { MultiSelect, type SelectOption } from '../components/common/MultiSelect'
import { formatError } from '../lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '../lib/normalize'
import type { SearchCategory, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '../types'
import styles from './SearchPage.module.scss'

const TABS: { key: SearchCategory; labelKey: string; icon: typeof FileText }[] = [
  { key: 'paper', labelKey: 'search.papers', icon: FileText },
  { key: 'patent', labelKey: 'search.patents', icon: Shield },
  { key: 'web', labelKey: 'search.web', icon: Globe },
]

const SOURCE_OPTIONS: Record<SearchCategory, SelectOption[]> = {
  paper: [
    { value: 'openalex', label: 'OpenAlex', description: '开放学术图谱' },
    { value: 'semantic_scholar', label: 'Semantic Scholar', description: '可选 Key 提速' },
    { value: 'crossref', label: 'Crossref', description: 'DOI 权威源' },
    { value: 'arxiv', label: 'arXiv', description: '预印本' },
    { value: 'dblp', label: 'DBLP', description: '计算机科学索引' },
    { value: 'core', label: 'CORE', description: '全文开放获取', needsKey: true },
    { value: 'pubmed', label: 'PubMed', description: '生物医学' },
    { value: 'unpaywall', label: 'Unpaywall', description: 'OA 链接查找' },
  ],
  patent: [
    { value: 'patentsview', label: 'PatentsView', description: 'USPTO 美国专利' },
    { value: 'pqai', label: 'PQAI', description: '语义专利检索' },
    { value: 'epo_ops', label: 'EPO OPS', description: '欧洲专利 (OAuth)', needsKey: true },
    { value: 'uspto_odp', label: 'USPTO ODP', description: '官方 API', needsKey: true },
    { value: 'the_lens', label: 'The Lens', description: '全球专利+论文', needsKey: true },
    { value: 'cnipa', label: 'CNIPA', description: '中国知识产权局', needsKey: true },
    { value: 'patsnap', label: 'PatSnap', description: '智慧芽', needsKey: true },
    { value: 'google_patents', label: 'Google Patents', description: '爬虫' },
  ],
  web: [
    { value: 'duckduckgo', label: 'DuckDuckGo', description: '爬虫' },
    { value: 'yahoo', label: 'Yahoo', description: '爬虫' },
    { value: 'brave', label: 'Brave', description: '爬虫' },
    { value: 'google', label: 'Google', description: '爬虫, 高风险' },
    { value: 'bing', label: 'Bing', description: '爬虫' },
    { value: 'searxng', label: 'SearXNG', description: '元搜索 (需自建)' },
    { value: 'tavily', label: 'Tavily', description: 'AI 搜索', needsKey: true },
    { value: 'exa', label: 'Exa', description: '语义搜索', needsKey: true },
    { value: 'serper', label: 'Serper', description: 'Google SERP API', needsKey: true },
    { value: 'brave_api', label: 'Brave API', description: '官方 API', needsKey: true },
    { value: 'serpapi', label: 'SerpAPI', description: '多引擎 SERP', needsKey: true },
    { value: 'firecrawl', label: 'Firecrawl', description: '搜索+爬取', needsKey: true },
    { value: 'perplexity', label: 'Perplexity', description: 'Sonar AI 搜索', needsKey: true },
    { value: 'linkup', label: 'Linkup', description: '实时搜索', needsKey: true },
    { value: 'scrapingdog', label: 'ScrapingDog', description: 'SERP API', needsKey: true },
    { value: 'startpage', label: 'Startpage', description: '隐私搜索 (爬虫)' },
    { value: 'baidu', label: '百度', description: '百度搜索 (爬虫)' },
    { value: 'mojeek', label: 'Mojeek', description: '独立搜索 (爬虫)' },
    { value: 'yandex', label: 'Yandex', description: '搜索 (爬虫)' },
    { value: 'whoogle', label: 'Whoogle', description: 'Google 代理 (需自建)' },
    { value: 'websurfx', label: 'Websurfx', description: '元搜索 (需自建)' },
  ],
}

const DEFAULT_SELECTED: Record<SearchCategory, string[]> = {
  paper: ['openalex', 'arxiv'],
  patent: ['patentsview', 'pqai'],
  web: ['duckduckgo', 'yahoo', 'brave'],
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
  const [selections, setSelections] = useState<Record<SearchCategory, string[]>>({
    ...DEFAULT_SELECTED,
  })
  const [count, setCount] = useState(10)
  const [loading, setLoading] = useState(false)
  const [paperResults, setPaperResults] = useState<SearchResponse | null>(null)
  const [patentResults, setPatentResults] = useState<SearchResponse | null>(null)
  const [webResults, setWebResults] = useState<WebSearchResponse | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)

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

  const handleSearch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!canSearch) return
      setLoading(true)
      const joined = currentSources.join(',')
      try {
        if (tab === 'paper') {
          setPaperResults(null)
          const res = await api.searchPaper(query, joined, count)
          setPaperResults(res)
          addToast('success', t('search.success', { count: res.total }))
        } else if (tab === 'patent') {
          setPatentResults(null)
          const res = await api.searchPatent(query, joined, count)
          setPatentResults(res)
          addToast('success', t('search.success', { count: res.total }))
        } else {
          setWebResults(null)
          const res = await api.searchWeb(query, joined, count)
          setWebResults(res)
          addToast('success', t('search.success', { count: res.total_results }))
        }
      } catch (err) {
        addToast('error', t('search.failed', { message: formatError(err) }))
      } finally {
        setLoading(false)
      }
    },
    [tab, query, currentSources, canSearch, count, addToast, t],
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
    return (
      <m.div key={i} className={styles.resultCard} variants={staggerItem}>
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
          <div className={styles.resultCount}>{t('search.resultCount', { count: webResults.total_results })}</div>
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
          <button type="submit" className="btn btn-primary" disabled={loading || !canSearch}>
            {loading ? t('search.searching') : t('search.button')}
          </button>
        </div>
        <div className={styles.sourceRow}>
          <MultiSelect
            options={SOURCE_OPTIONS[tab]}
            selected={currentSources}
            onChange={handleSelectionChange}
            placeholder={tab === 'web' ? t('search.engines') : t('search.sources')}
          />
        </div>
      </form>

      <div className={styles.results}>{renderResults()}</div>
    </div>
  )
}
