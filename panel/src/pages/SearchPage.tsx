import { useState, useCallback, type FormEvent } from 'react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Spinner } from '../components/common/Spinner'
import type { SearchCategory, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '../types'
import styles from './SearchPage.module.scss'

const TABS: { key: SearchCategory; label: string }[] = [
  { key: 'paper', label: '论文' },
  { key: 'patent', label: '专利' },
  { key: 'web', label: '网页' },
]

const DEFAULT_SOURCES: Record<SearchCategory, string> = {
  paper: 'openalex,arxiv',
  patent: 'patentsview,pqai',
  web: 'duckduckgo,yahoo,brave',
}

export function SearchPage() {
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
        } else if (tab === 'patent') {
          const res = await api.searchPatent(query, sources, count)
          setPatentResults(res)
        } else {
          const res = await api.searchWeb(query, sources, count)
          setWebResults(res)
        }
        addToast('success', '搜索完成')
      } catch (err) {
        addToast('error', `搜索失败: ${err instanceof Error ? err.message : '未知错误'}`)
      } finally {
        setLoading(false)
      }
    },
    [tab, query, sources, count, addToast],
  )

  const renderPaperCard = (p: PaperResult, i: number) => (
    <div key={i} className={styles.resultCard}>
      <div className={styles.resultTitle}>
        {p.url ? (
          <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || '无标题'}</a>
        ) : (
          p.title || '无标题'
        )}
      </div>
      <div className={styles.resultMeta}>
        {p.authors && p.authors.length > 0 && (
          <span>👤 {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? ' 等' : ''}</span>
        )}
        {p.year && <span>📅 {p.year}</span>}
        {p.doi && <span>DOI: {p.doi}</span>}
        {p.source && <span className={styles.sourceTag}>{p.source}</span>}
      </div>
      {p.abstract && (
        <div className={styles.resultAbstract}>
          {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
        </div>
      )}
    </div>
  )

  const renderPatentCard = (p: PatentResult, i: number) => (
    <div key={i} className={styles.resultCard}>
      <div className={styles.resultTitle}>
        {p.url ? (
          <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title || '无标题'}</a>
        ) : (
          p.title || '无标题'
        )}
      </div>
      <div className={styles.resultMeta}>
        {p.patent_number && <span>📋 {p.patent_number}</span>}
        {p.assignee && <span>🏢 {p.assignee}</span>}
        {p.date && <span>📅 {p.date}</span>}
        {p.source && <span className={styles.sourceTag}>{p.source}</span>}
      </div>
      {p.abstract && (
        <div className={styles.resultAbstract}>
          {p.abstract.slice(0, 300)}{p.abstract.length > 300 ? '...' : ''}
        </div>
      )}
    </div>
  )

  const renderWebCard = (item: WebResult, i: number) => (
    <div key={i} className={styles.resultCard}>
      <div className={styles.resultTitle}>
        <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
      </div>
      <div className={styles.resultUrl}>{item.url}</div>
      {item.snippet && <div className={styles.resultAbstract}>{item.snippet}</div>}
      {item.engine && <span className={styles.sourceTag}>{item.engine}</span>}
    </div>
  )

  const renderResults = () => {
    if (loading) return <Spinner size="lg" label="搜索中..." />

    if (tab === 'paper' && paperResults) {
      const allItems = paperResults.results.flatMap((r) => r.results) as PaperResult[]
      if (allItems.length === 0) return <div className={styles.empty}>未找到结果</div>
      return (
        <div>
          <div className={styles.resultCount}>共 {paperResults.total} 条结果</div>
          {allItems.map((item, i) => renderPaperCard(item, i))}
        </div>
      )
    }

    if (tab === 'patent' && patentResults) {
      const allItems = patentResults.results.flatMap((r) => r.results) as PatentResult[]
      if (allItems.length === 0) return <div className={styles.empty}>未找到结果</div>
      return (
        <div>
          <div className={styles.resultCount}>共 {patentResults.total} 条结果</div>
          {allItems.map((item, i) => renderPatentCard(item, i))}
        </div>
      )
    }

    if (tab === 'web' && webResults) {
      if (webResults.results.length === 0) return <div className={styles.empty}>未找到结果</div>
      return (
        <div>
          <div className={styles.resultCount}>共 {webResults.total} 条结果</div>
          {webResults.results.map((item, i) => renderWebCard(item, i))}
        </div>
      )
    }

    return <div className={styles.empty}>输入关键词开始搜索</div>
  }

  return (
    <div className={styles.page}>
      {/* Tabs */}
      <div className={styles.tabs}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`${styles.tab} ${tab === t.key ? styles.active : ''}`}
            onClick={() => handleTabChange(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Search Form */}
      <form className={styles.form} onSubmit={handleSearch}>
        <div className={styles.formRow}>
          <input
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入搜索关键词..."
            required
          />
          <input
            className={styles.inputSm}
            type="text"
            value={sources}
            onChange={(e) => setSources(e.target.value)}
            placeholder={tab === 'web' ? '搜索引擎' : '数据源'}
          />
          <select
            className={styles.select}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {n} 条
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '搜索中...' : '搜索'}
          </button>
        </div>
      </form>

      {/* Results */}
      <div className={styles.results}>{renderResults()}</div>
    </div>
  )
}
