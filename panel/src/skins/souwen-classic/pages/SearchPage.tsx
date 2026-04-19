/**
 * 搜索页面 - 论文/专利/网页综合搜索
 *
 * 文件用途：提供统一的搜索界面，支持三个搜索类别（paper/patent/web）、数据源选择、结果展示和过滤
 *
 * 核心功能模块：
 *   - 搜索类别切换：分段控制器在三个类别间切换
 *   - 数据源选择：多选器选择每个类别的数据源
 *   - 搜索输入：关键词输入框 + 搜索建议
 *   - 结果展示：动画列表显示各数据源的搜索结果
 *   - 状态管理：加载中、错误、空结果、成功等状态
 *   - 竞态处理：新搜索自动取消前一个请求
 *
 * 常量定义：
 *   SOURCE_ICONS - 数据源名称到图标组件的映射
 *   DEFAULT_SELECTED - 默认选中的数据源
 *   SEARCH_SUGGESTIONS - 搜索建议词列表
 *
 * 主要交互：
 *   - 选择搜索类别 → 加载对应类别的数据源
 *   - 选择数据源 → 更新搜索配置
 *   - 输入关键词 → 显示搜索建议
 *   - 点击搜索 → 并发调用各数据源的搜索 API
 *   - 处理竞态：新搜索覆盖前一个搜索
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  FileText, Shield, Globe, Users, Calendar, Link, Building,
  Search, ExternalLink, Sparkles, BookOpen, Database, Library,
  GraduationCap, Unlock, Heart, CheckCircle2, Circle,
  SlidersHorizontal, Command, Settings,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { Badge } from '../components/common/Badge'
import { formatError } from '@core/lib/errors'
import { normalizePaper, normalizePatent, normalizeWeb } from '@core/lib/normalize'
import type { SearchCategory, SourceInfo, SearchResponse, WebSearchResponse, WebResult, PaperResult, PatentResult } from '@core/types'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './SearchPage.module.scss'

/* ─── Source icon mapping ─── */
/** 数据源名称到 Lucide 图标组件的映射表，用于在 UI 中可视化各数据源 */
const SOURCE_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  openalex: Library,
  arxiv: BookOpen,
  semantic_scholar: Sparkles,
  crossref: Database,
  core: BookOpen,
  pubmed: Heart,
  dblp: GraduationCap,
  unpaywall: Unlock,
  google_patents: Shield,
  patentsview: FileText,
  pqai: Search,
  epo_ops: Shield,
  uspto_odp: Shield,
  the_lens: Search,
  cnipa: Shield,
  patsnap: Shield,
}

/** 根据数据源名称返回对应图标组件，未注册的数据源使用 Globe 作为兜底 */
function getSourceIcon(name: string): React.ComponentType<{ size?: number }> {
  return SOURCE_ICONS[name] ?? Globe
}

interface SourceOption {
  value: string
  label: string
  description?: string
  needsKey?: boolean
}

/** 将后端返回的 SourceInfo 列表转换为下拉选项格式 */
function toSourceOptions(sources: SourceInfo[]): SourceOption[] {
  return sources.map((s) => ({
    value: s.name,
    label: s.name,
    description: s.description,
    needsKey: s.needs_key,
  }))
}

/** 当 API 返回的数据源列表为空时使用的兜底选项（保证 UI 始终有可选项） */
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

// SEARCH_SUGGESTIONS 已移至组件内部以支持 i18n

/** 解析某分类的数据源选项：API 有数据时使用 API，否则回退到默认选项 */
function resolveSourceOptions(
  category: SearchCategory,
  sources: SourceInfo[],
  fallback: Record<SearchCategory, SourceOption[]>,
): SourceOption[] {
  const options = toSourceOptions(sources)
  return options.length > 0 ? options : fallback[category]
}

/**
 * 净化用户的数据源选择：移除不再可用的源，若清空则回退到默认值
 * 用途：在 API 返回新的数据源列表后，确保用户的选择只包含合法值
 */
function sanitizeSelections(
  current: Record<SearchCategory, string[]>,
  options: Record<SearchCategory, SourceOption[]>,
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

/**
 * 搜索状态机：idle（空闲）→ loading（搜索中）→ error（失败） / 成功后回到 idle
 * tab 字段记录正在搜索的分类，用于实现"切换 tab 不影响其他 tab 状态"
 */
type SearchState =
  | { status: 'idle'; tab: null; message: null }
  | { status: 'loading'; tab: SearchCategory; message: null }
  | { status: 'error'; tab: SearchCategory; message: string }

/**
 * SearchPage 主组件
 * 状态：当前分类 tab、查询词 query、各分类数据源选项与选择、三类结果（论文/专利/网页）
 * 关键机制：
 *   - 通过 activeRequestRef + requestIdRef 实现请求竞态控制（新请求会取消上一个未完成的请求）
 *   - 卸载时自动 abort 进行中的请求，防止 setState on unmounted
 */
export function SearchPage() {
  const { t } = useTranslation()
  const SEARCH_SUGGESTIONS = [
    t('search.suggestion1', '大语言模型'),
    t('search.suggestion2', '量子计算'),
    t('search.suggestion3', 'CRISPR 基因编辑'),
    t('search.suggestion4', 'Transformer 架构'),
    t('search.suggestion5', '气候变化'),
    t('search.suggestion6', '神经辐射场'),
  ]
  const fallbackOptions = makeFallbackOptions(t)
  const [tab, setTab] = useState<SearchCategory>('paper')
  const [query, setQuery] = useState('')
  const [sourceOptions, setSourceOptions] = useState<Record<SearchCategory, SourceOption[]>>(fallbackOptions)
  const [selections, setSelections] = useState<Record<SearchCategory, string[]>>({
    ...DEFAULT_SELECTED,
  })
  const [count, setCount] = useState(10)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [timeout, setTimeout_] = useState<number | undefined>(undefined)
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

  const toggleSource = useCallback((sourceName: string) => {
    setSelections((prev) => {
      const curr = prev[tab]
      const next = curr.includes(sourceName)
        ? curr.filter((s) => s !== sourceName)
        : [...curr, sourceName]
      return { ...prev, [tab]: next }
    })
  }, [tab])

  const selectAllSources = useCallback(() => {
    setSelections((prev) => ({
      ...prev,
      [tab]: sourceOptions[tab].map((s) => s.value),
    }))
  }, [tab, sourceOptions])

  const clearAllSources = useCallback(() => {
    setSelections((prev) => ({ ...prev, [tab]: [] }))
  }, [tab])

  const currentSources = selections[tab]
  const canSearch = query.trim().length > 0 && currentSources.length > 0
  const isSearchingCurrentTab = searchState.status === 'loading' && searchState.tab === tab
  const maxPerPage = tab === 'web' ? 50 : 100

  /* ─── Keyboard shortcut ⌘K ─── */
  /** ⌘K / Ctrl+K 快捷键：聚焦搜索输入框 */
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  /**
   * 处理搜索提交
   * 关键逻辑：
   *   1. 生成单调递增的 requestId 并 abort 上一个进行中的请求（竞态保护）
   *   2. 根据当前 tab 调用对应分类的 API（searchPaper/searchPatent/searchWeb）
   *   3. 检查 activeRequestRef.id === requestId 才更新结果，避免老请求覆盖新结果
   *   4. abort 错误被静默忽略（仅展示真实失败）
   */
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

    return null
  }

  return (
    <div className={styles.page}>
      {/* ─── Hero Title (only when no results) ─── */}
      {!hasResults && (
        <m.div className={styles.heroTitle} {...fadeInUp}>
          <h1 className={styles.heroHeading}>{t('search.heroTitle')}</h1>
          <p className={styles.heroSubtitle}>{t('search.heroSubtitle')}</p>
        </m.div>
      )}

      {/* ─── Command Center Card ─── */}
      <m.div className={`${styles.commandCard} ${hasResults ? styles.compact : ''}`} {...fadeInUp}>
        {/* Top bar: tabs + ⌘K hint */}
        <div className={styles.commandHeader}>
          <div className={styles.tabGroup}>
            {(['paper', 'patent', 'web'] as SearchCategory[]).map((key) => {
              const icons = { paper: FileText, patent: Shield, web: Globe }
              const labels = {
                paper: t('search.papers'),
                patent: t('search.patents'),
                web: t('search.web'),
              }
              const Icon = icons[key]
              return (
                <button
                  key={key}
                  type="button"
                  className={`${styles.tabBtn} ${tab === key ? styles.tabActive : ''}`}
                  onClick={() => handleTabChange(key)}
                >
                  <Icon size={15} />
                  {labels[key]}
                </button>
              )
            })}
          </div>
          <div className={styles.shortcutHint}>
            <Command size={12} />
            <span>K</span>
          </div>
        </div>

        {/* Search input row */}
        <m.form className={styles.searchForm} onSubmit={handleSearch} aria-busy={isSearchingCurrentTab}>
          <div className={styles.searchBar}>
            <Sparkles size={20} className={styles.searchIcon} />
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
              aria-label={t('search.button')}
            >
              {isSearchingCurrentTab ? t('search.searching') : t('search.button')}
            </button>
          </div>
        </m.form>

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

        {/* Source cards section (collapsible when has results) */}
        {!hasResults && (
          <div className={styles.sourceSection}>
            <div className={styles.sourceSectionHeader}>
              <div className={styles.sourceSectionLeft}>
                <SlidersHorizontal size={16} />
                <span className={styles.sourceSectionTitle}>{t('search.searchScope')}</span>
                <Badge color="indigo">{t('search.selectedCount', { count: currentSources.length })}</Badge>
              </div>
              <div className={styles.sourceSectionActions}>
                <button type="button" className={styles.sourceActionBtn} onClick={selectAllSources}>
                  {t('search.selectAll')}
                </button>
                <button type="button" className={styles.sourceActionBtn} onClick={clearAllSources}>
                  {t('search.clearAll')}
                </button>
              </div>
            </div>
            <div className={styles.sourceGrid}>
              {sourceOptions[tab].map((source) => {
                const isSelected = currentSources.includes(source.value)
                const Icon = getSourceIcon(source.value)
                return (
                  <button
                    key={source.value}
                    type="button"
                    className={`${styles.sourceCard} ${isSelected ? styles.sourceCardActive : ''}`}
                    onClick={() => toggleSource(source.value)}
                  >
                    <div className={styles.sourceCardTop}>
                      <span className={styles.sourceCardIcon}>
                        <Icon size={18} />
                      </span>
                      {isSelected
                        ? <CheckCircle2 size={20} className={styles.sourceCheck} />
                        : <Circle size={20} className={styles.sourceUncheck} />
                      }
                    </div>
                    <div className={styles.sourceCardName}>{source.label}</div>
                    {source.description && (
                      <div className={styles.sourceCardDesc}>{source.description}</div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </m.div>

      {/* ─── Suggestion chips (only when idle / no results) ─── */}
      {!hasResults && searchState.status === 'idle' && (
        <m.div className={styles.suggestions} {...fadeInUp}>
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
        </m.div>
      )}

      {/* ─── Results ─── */}
      <div className={styles.results} aria-live="polite">
        {renderResults()}
      </div>
    </div>
  )
}
