/**
 * 文件用途：Carbon 皮肤的搜索页面，支持跨多个数据源的统一搜索（论文、专利、网页）
 *
 * 组件/函数清单：
 *   SearchPage（函数组件）
 *     - 功能：提供搜索表单、数据源选择、结果展示，支持论文/专利/网页搜索
 *       1. 搜索输入和建议
 *       2. 按数据源类别（论文/专利/网页）分组选择来源
 *       3. 异步执行搜索，展示结果列表或错误状态
 *     - State 状态：query (string) 搜索词, selectedSources (Record) 各类别选中来源, results (Record) 搜索结果
 *     - 关键钩子：useTranslation 翻译, useNotificationStore 提示
 *     - 关键函数：handleSearch 执行搜索, normalizePaper/normalizePatent/normalizeWeb 结果格式化
 *
 *   toSourceOptions（函数）
 *     - 功能：将 SourceInfo 数组转换为下拉选项格式
 *   makeFallbackOptions（函数）
 *     - 功能：生成默认数据源选项（当服务器数据不可用时使用）
 *   resolveSourceOptions（函数）
 *     - 功能：根据类别获取可用数据源选项
 *
 * 模块依赖：
 *   - react: 状态和表单处理
 *   - react-i18next: 国际化翻译
 *   - framer-motion: 动画
 *   - lucide-react: 图标
 *   - @core/services/api: 搜索 API
 *   - @core/lib/normalize: 搜索结果格式化函数
 *   - SearchPage.module.scss: 页面样式
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  FileText, Users, Calendar, Link, Building, Globe,
  Cpu, ExternalLink, Settings,
  List, LayoutGrid, Grid3X3, Download,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '@core/lib/normalize'
import { extractDomain } from '@core/lib/url'
import { exportPapers, exportPatents, exportWebResults, type ExportFormat } from '@core/lib/export'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import type {
  SearchCategory, SourceInfo, SearchResponse, WebSearchResponse,
  WebResult, PaperResult, PatentResult,
} from '@core/types'
import styles from './SearchPage.module.scss'

type LayoutMode = 'list' | 'card' | 'grid'

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

function makeSearchSuggestions(t: (key: string) => string): string[] {
  return [
    t('search.suggestion1'),
    t('search.suggestion2'),
    t('search.suggestion3'),
    t('search.suggestion4'),
    t('search.suggestion5'),
    t('search.suggestion6'),
  ]
}

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
  const SEARCH_SUGGESTIONS = makeSearchSuggestions(t)
  const [tab, setTab] = useState<SearchCategory>('paper')
  const [query, setQuery] = useState('')
  const [sourceOptions, setSourceOptions] = useState<Record<SearchCategory, SourceOption[]>>(fallbackOptions)
  const [selections, setSelections] = useState<Record<SearchCategory, string[]>>({ ...DEFAULT_SELECTED })
  const [count, setCount] = useState(10)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [timeout, setTimeout_] = useState<number | undefined>(undefined)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('card')
  const [searchState, setSearchState] = useState<SearchState>({ status: 'idle', tab: null, message: null })
  const [paperResults, setPaperResults] = useState<SearchResponse | null>(null)
  const [patentResults, setPatentResults] = useState<SearchResponse | null>(null)
  const [webResults, setWebResults] = useState<WebSearchResponse | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)
  const activeRequestRef = useRef<{ id: number; controller: AbortController } | null>(null)
  const requestIdRef = useRef(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // 获取服务器可用的数据源列表，初始化选项，支持取消机制
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

  // 组件卸载时取消未完成的 API 请求
  useEffect(() => {
    return () => { activeRequestRef.current?.controller.abort() }
  }, [])

  // 切换指定数据源的选中状态（添加或移除）
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
  const maxPerPage = tab === 'web' ? 50 : 100

  // 执行搜索请求：根据当前标签页类型调用相应的 API，支持请求取消和去重
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
        // 根据选中的标签页类型执行不同的搜索 API
        if (tab === 'paper') {
          setPaperResults(null)
          const res = await api.searchPaper(query, joined, count, controller.signal, timeout)
          if (activeRequestRef.current?.id !== requestId) return
          setPaperResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total }))
        } else if (tab === 'patent') {
          setPatentResults(null)
          const res = await api.searchPatent(query, joined, count, controller.signal, timeout)
          if (activeRequestRef.current?.id !== requestId) return
          setPatentResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total }))
        } else {
          setWebResults(null)
          const res = await api.searchWeb(query, joined, count, controller.signal, timeout)
          if (activeRequestRef.current?.id !== requestId) return
          setWebResults(res)
          setSearchState({ status: 'idle', tab: null, message: null })
          addToast('success', t('search.success', { count: res.total_results }))
        }
      } catch (err) {
        // 忽略被取消或过期的请求的错误
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
    [tab, query, currentSources, canSearch, count, timeout, addToast, t],
  )

  // 重试搜索按钮的处理函数
  const handleRetry = useCallback(() => {
    const syntheticEvent = { preventDefault: () => {} } as FormEvent
    handleSearch(syntheticEvent)
  }, [handleSearch])

  // 渲染论文结果卡片，格式化作者、年份、DOI 等元数据
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

  // 渲染专利结果卡片，展示专利号、申请人、公开日期等信息
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

  // 渲染网页结果卡片，展示标题、URL、搜索引擎来源和摘要
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
        {item.url && <div className={styles.resultUrl}><Globe size={12} /> {extractDomain(item.url)}</div>}
        {item.snippet && <p className={styles.resultAbstract}>{item.snippet}</p>}
      </m.article>
    )
  }

  /* ─── List mode renderers (single-line, dense) ─── */
  const renderPaperListItem = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    const key = p.doi || `paper-list-${p.source}-${i}`
    const domain = p.url ? extractDomain(p.url) : ''
    const authorStr = p.authors.slice(0, 3).join(', ') + (p.authors.length > 3 ? '…' : '')
    return (
      <div key={key} className={styles.resultListItem}>
        {p.source && <span className={styles.badge}>{p.source}</span>}
        <span className={styles.listTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">
              {p.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            p.title || t('search.untitled')
          )}
        </span>
        {authorStr && <span className={styles.listMeta}>— {authorStr}</span>}
        {p.year && <span className={styles.listMeta}>— {p.year}</span>}
        {domain && <span className={styles.listDomain} title={p.url}>— {domain}</span>}
      </div>
    )
  }

  const renderPatentListItem = (raw: PatentResult, i: number) => {
    const p = normalizePatent(raw)
    const key = p.patentNumber || `patent-list-${p.source}-${i}`
    const domain = p.url ? extractDomain(p.url) : ''
    return (
      <div key={key} className={styles.resultListItem}>
        {p.source && <span className={styles.badge}>{p.source}</span>}
        <span className={styles.listTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">
              {p.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            p.title || t('search.untitled')
          )}
        </span>
        {p.patentNumber && <span className={styles.listMeta}>— {p.patentNumber}</span>}
        {p.applicant && <span className={styles.listMeta}>— {p.applicant}</span>}
        {p.publicationDate && <span className={styles.listMeta}>— {p.publicationDate}</span>}
        {domain && <span className={styles.listDomain} title={p.url}>— {domain}</span>}
      </div>
    )
  }

  const renderWebListItem = (raw: WebResult, i: number) => {
    const item = normalizeWeb(raw)
    const key = item.url || `web-list-${item.source}-${i}`
    const domain = item.url ? extractDomain(item.url) : ''
    const snippet = item.snippet.length > 80 ? item.snippet.slice(0, 80) + '…' : item.snippet
    return (
      <div key={key} className={styles.resultListItem}>
        {(item.source || raw.engine) && <span className={styles.badge}>{item.source || raw.engine}</span>}
        <span className={styles.listTitle}>
          {item.url ? (
            <a href={item.url} target="_blank" rel="noopener noreferrer">
              {item.title}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            item.title
          )}
        </span>
        {domain && <span className={styles.listDomain} title={item.url}>— {domain}</span>}
        {snippet && <span className={styles.listMeta}>— {snippet}</span>}
      </div>
    )
  }

  /* ─── Grid mode renderers (compact NxN cards) ─── */
  const renderPaperGridCard = (raw: PaperResult, i: number) => {
    const p = normalizePaper(raw)
    const key = p.doi || `paper-grid-${p.source}-${i}`
    const domain = p.url ? extractDomain(p.url) : ''
    return (
      <m.article key={key} className={styles.resultGridCard} variants={staggerItem}>
        <div className={styles.gridCardHeader}>
          {p.source && <span className={styles.badge}>{p.source}</span>}
          {domain && <span className={styles.gridDomain} title={p.url}><Globe size={11} /> {domain}</span>}
        </div>
        <h3 className={styles.gridCardTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">
              {p.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            p.title || t('search.untitled')
          )}
        </h3>
        {p.abstract && <p className={styles.gridCardAbstract}>{p.abstract}</p>}
      </m.article>
    )
  }

  const renderPatentGridCard = (raw: PatentResult, i: number) => {
    const p = normalizePatent(raw)
    const key = p.patentNumber || `patent-grid-${p.source}-${i}`
    const domain = p.url ? extractDomain(p.url) : ''
    return (
      <m.article key={key} className={styles.resultGridCard} variants={staggerItem}>
        <div className={styles.gridCardHeader}>
          {p.source && <span className={styles.badge}>{p.source}</span>}
          {domain && <span className={styles.gridDomain} title={p.url}><Globe size={11} /> {domain}</span>}
        </div>
        <h3 className={styles.gridCardTitle}>
          {p.url ? (
            <a href={p.url} target="_blank" rel="noopener noreferrer">
              {p.title || t('search.untitled')}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            p.title || t('search.untitled')
          )}
        </h3>
        {p.abstract && <p className={styles.gridCardAbstract}>{p.abstract}</p>}
      </m.article>
    )
  }

  const renderWebGridCard = (raw: WebResult, i: number) => {
    const item = normalizeWeb(raw)
    const key = item.url || `web-grid-${item.source}-${i}`
    const domain = item.url ? extractDomain(item.url) : ''
    return (
      <m.article key={key} className={styles.resultGridCard} variants={staggerItem}>
        <div className={styles.gridCardHeader}>
          {(item.source || raw.engine) && <span className={styles.badge}>{item.source || raw.engine}</span>}
          {domain && <span className={styles.gridDomain} title={item.url}><Globe size={11} /> {domain}</span>}
        </div>
        <h3 className={styles.gridCardTitle}>
          {item.url ? (
            <a href={item.url} target="_blank" rel="noopener noreferrer">
              {item.title}
              <ExternalLink size={12} className={styles.externalIcon} />
            </a>
          ) : (
            item.title
          )}
        </h3>
        {item.snippet && <p className={styles.gridCardAbstract}>{item.snippet}</p>}
      </m.article>
    )
  }

  /* ─── Export handler ─── */
  const handleExport = useCallback((format: ExportFormat) => {
    let exportedCount = 0
    if (tab === 'paper' && paperResults) {
      const items = (paperResults.results.flatMap((r) => r.results) as PaperResult[]).map(normalizePaper)
      exportedCount = items.length
      exportPapers(items, format)
    } else if (tab === 'patent' && patentResults) {
      const items = (patentResults.results.flatMap((r) => r.results) as PatentResult[]).map(normalizePatent)
      exportedCount = items.length
      exportPatents(items, format)
    } else if (tab === 'web' && webResults) {
      const items = webResults.results.map(normalizeWeb)
      exportedCount = items.length
      exportWebResults(items, format)
    }
    if (exportedCount > 0) {
      addToast('success', t('search.exported', { count: exportedCount }))
    }
  }, [tab, paperResults, patentResults, webResults, addToast, t])

  const hasResults =
    (tab === 'paper' && paperResults) ||
    (tab === 'patent' && patentResults) ||
    (tab === 'web' && webResults)

  // 统一处理搜索结果渲染逻辑：加载中、错误、论文/专利/网页结果三种状态
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

    const renderToolbar = (totalCount: number) => (
      <div className={styles.resultsToolbar}>
        <div className={styles.resultCount}>{t('search.resultCount', { count: totalCount })}</div>
        <div className={styles.toolbarActions}>
          <div className={styles.layoutToggle} role="group" aria-label={t('search.layoutCard')}>
            <button
              type="button"
              className={`${styles.layoutBtn} ${layoutMode === 'list' ? styles.layoutBtnActive : ''}`}
              onClick={() => setLayoutMode('list')}
              aria-label={t('search.layoutList')}
              title={t('search.layoutList')}
            >
              <List size={14} />
            </button>
            <button
              type="button"
              className={`${styles.layoutBtn} ${layoutMode === 'card' ? styles.layoutBtnActive : ''}`}
              onClick={() => setLayoutMode('card')}
              aria-label={t('search.layoutCard')}
              title={t('search.layoutCard')}
            >
              <LayoutGrid size={14} />
            </button>
            <button
              type="button"
              className={`${styles.layoutBtn} ${layoutMode === 'grid' ? styles.layoutBtnActive : ''}`}
              onClick={() => setLayoutMode('grid')}
              aria-label={t('search.layoutGrid')}
              title={t('search.layoutGrid')}
            >
              <Grid3X3 size={14} />
            </button>
          </div>
          <div className={styles.exportGroup} role="group" aria-label={t('search.exportTitle')}>
            <button
              type="button"
              className={styles.exportBtn}
              onClick={() => handleExport('csv')}
              title={t('search.exportCSV')}
            >
              <Download size={13} /> {t('search.exportCSV')}
            </button>
            <button
              type="button"
              className={styles.exportBtn}
              onClick={() => handleExport('xls')}
              title={t('search.exportXLS')}
            >
              <Download size={13} /> {t('search.exportXLS')}
            </button>
          </div>
        </div>
      </div>
    )

    if (tab === 'paper' && paperResults) {
      const allItems = paperResults.results.flatMap((r) => r.results) as PaperResult[]
      if (allItems.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      if (layoutMode === 'list') {
        return (
          <div>
            {renderToolbar(paperResults.total)}
            <div className={styles.resultList}>
              {allItems.map((item, i) => renderPaperListItem(item, i))}
            </div>
          </div>
        )
      }
      if (layoutMode === 'grid') {
        return (
          <div>
            {renderToolbar(paperResults.total)}
            <m.div className={styles.resultGrid} variants={staggerContainer} initial="initial" animate="animate">
              {allItems.map((item, i) => renderPaperGridCard(item, i))}
            </m.div>
          </div>
        )
      }
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          {renderToolbar(paperResults.total)}
          {allItems.map((item, i) => renderPaperCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'patent' && patentResults) {
      const allItems = patentResults.results.flatMap((r) => r.results) as PatentResult[]
      if (allItems.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      if (layoutMode === 'list') {
        return (
          <div>
            {renderToolbar(patentResults.total)}
            <div className={styles.resultList}>
              {allItems.map((item, i) => renderPatentListItem(item, i))}
            </div>
          </div>
        )
      }
      if (layoutMode === 'grid') {
        return (
          <div>
            {renderToolbar(patentResults.total)}
            <m.div className={styles.resultGrid} variants={staggerContainer} initial="initial" animate="animate">
              {allItems.map((item, i) => renderPatentGridCard(item, i))}
            </m.div>
          </div>
        )
      }
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          {renderToolbar(patentResults.total)}
          {allItems.map((item, i) => renderPatentCard(item, i))}
        </m.div>
      )
    }

    if (tab === 'web' && webResults) {
      if (webResults.results.length === 0) return <div className={styles.errorState}>{t('search.noResults')}</div>
      if (layoutMode === 'list') {
        return (
          <div>
            {renderToolbar(webResults.total_results)}
            <div className={styles.resultList}>
              {webResults.results.map((item, i) => renderWebListItem(item, i))}
            </div>
          </div>
        )
      }
      if (layoutMode === 'grid') {
        return (
          <div>
            {renderToolbar(webResults.total_results)}
            <m.div className={styles.resultGrid} variants={staggerContainer} initial="initial" animate="animate">
              {webResults.results.map((item, i) => renderWebGridCard(item, i))}
            </m.div>
          </div>
        )
      }
      return (
        <m.div variants={staggerContainer} initial="initial" animate="animate">
          {renderToolbar(webResults.total_results)}
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
          <div className={styles.gridOverlay} />
          <h1 className={styles.heroTitle}>{t('app.name')}</h1>
          <p className={styles.heroSubtitle}>
            <Cpu size={14} />
            {t('search.subtitle')}
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
                [{TAB_LABELS[key]}]
              </button>
            ))}
          </div>

          {/* Search */}
          <form className={styles.searchForm} onSubmit={handleSearch}>
            <div className={styles.searchBar}>
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
                {isSearchingCurrentTab ? t('search.searching') : t('search.searchBtn')}
              </button>
            </div>
          </form>

          {/* Advanced search panel */}
          <div className={styles.advancedToggle}>
            <button
              type="button"
              className={styles.advancedToggleBtn}
              onClick={() => setShowAdvanced((v) => !v)}
            >
              <Settings size={14} />
              {t('advancedSearch.title')}
            </button>
          </div>
          {showAdvanced && (
            <div className={styles.advancedPanel}>
              <div className={styles.advancedField}>
                <label className={styles.advancedLabel}>
                  {t('advancedSearch.perPage')}: <strong>{count}</strong>
                </label>
                <input
                  type="range"
                  min={1}
                  max={maxPerPage}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  className={styles.slider}
                />
                <div className={styles.rangeHint}>
                  {t('advancedSearch.perPageHint', { max: maxPerPage })}
                </div>
              </div>
              <div className={styles.advancedField}>
                <label className={styles.advancedLabel}>{t('advancedSearch.timeout')}</label>
                <input
                  type="number"
                  className={styles.numberInput}
                  min={1}
                  max={300}
                  value={timeout ?? ''}
                  onChange={(e) => {
                    const v = e.target.value
                    setTimeout_(v === '' ? undefined : Number(v))
                  }}
                  placeholder={t('advancedSearch.timeoutPlaceholder')}
                />
              </div>
              <button
                type="button"
                className={styles.resetBtn}
                onClick={() => { setCount(10); setTimeout_(undefined) }}
              >
                {t('advancedSearch.reset')}
              </button>
            </div>
          )}

          {/* Source toggles */}
          <div className={styles.sourceSection}>
            <div className={styles.sourceLabel}>{t('search.dataSources')}:</div>
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
                [{TAB_LABELS[key]}]
              </button>
            ))}
          </div>
          <form className={styles.searchForm} onSubmit={handleSearch} style={{ maxWidth: '100%' }}>
            <div className={styles.searchBar}>
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
                {isSearchingCurrentTab ? t('search.searching') : t('search.searchBtn')}
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
