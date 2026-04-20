/**
 * 网页抓取页面 - 批量抓取网页内容
 *
 * 文件用途：提供网页内容抓取界面，支持多 URL 输入、多种抓取提供商、结果展示和导出
 *
 * 核心功能模块：
 *   - URL 输入：多行文本框支持批量输入 URL
 *   - 提供商选择：支持 builtin/jina_reader/tavily/firecrawl/exa 五种抓取引擎
 *   - 超时设置：可配置请求超时时间（默认 30 秒）
 *   - 结果展示：显示标题、URL、内容摘要，支持展开查看完整内容
 *   - 导出功能：支持复制内容、下载为 Markdown
 *   - 状态管理：加载中、错误、空结果、成功等状态
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Globe, ExternalLink, Copy, Download, CheckCircle2,
  AlertCircle, ChevronDown, ChevronUp, Sparkles,
  Settings, Link as LinkIcon,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { Badge } from '../components/common/Badge'
import { formatError } from '@core/lib/errors'
import type { FetchResponse, FetchResult } from '@core/types'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

const isSafeUrl = (url: string): boolean => /^https?:\/\//i.test(url)

const MAX_URLS = 20

type Provider = 'builtin' | 'jina_reader' | 'tavily' | 'firecrawl' | 'exa'

const PROVIDERS: { value: Provider; label: string; description: string }[] = [
  { value: 'builtin', label: 'Builtin', description: 'Built-in fetcher (default)' },
  { value: 'jina_reader', label: 'Jina Reader', description: 'Jina.ai Reader API' },
  { value: 'tavily', label: 'Tavily', description: 'Tavily Extract API' },
  { value: 'firecrawl', label: 'Firecrawl', description: 'Firecrawl scraping service' },
  { value: 'exa', label: 'Exa', description: 'Exa.ai content API' },
]

type FetchState =
  | { status: 'idle'; message: null }
  | { status: 'loading'; message: null }
  | { status: 'error'; message: string }

export function FetchPage() {
  const { t } = useTranslation()
  const [urls, setUrls] = useState('')
  const [provider, setProvider] = useState<Provider>('builtin')
  const [timeout, setTimeout_] = useState(30)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [fetchState, setFetchState] = useState<FetchState>({ status: 'idle', message: null })
  const [results, setResults] = useState<FetchResponse | null>(null)
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set())
  const addToast = useNotificationStore((s) => s.addToast)
  const activeRequestRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    return () => {
      activeRequestRef.current?.abort()
    }
  }, [])

  const parseUrls = (text: string): string[] => {
    return text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && (line.startsWith('http://') || line.startsWith('https://')))
  }

  const canFetch = parseUrls(urls).length > 0
  const isLoading = fetchState.status === 'loading'

  const handleFetch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!canFetch) return

      const urlList = parseUrls(urls)
      if (urlList.length === 0) {
        addToast('error', t('fetch.noValidUrls', 'No valid URLs found'))
        return
      }
      if (urlList.length > MAX_URLS) {
        addToast('error', t('fetch.tooManyUrls', { max: MAX_URLS, count: urlList.length }))
        return
      }

      activeRequestRef.current?.abort()
      const controller = new AbortController()
      activeRequestRef.current = controller

      setFetchState({ status: 'loading', message: null })
      setResults(null)
      setExpandedItems(new Set())

      try {
        const res = await api.fetch(urlList, provider, timeout, controller.signal)
        setResults(res)
        setFetchState({ status: 'idle', message: null })
        addToast('success', t('fetch.success', { count: res.total_ok, total: res.total }))
      } catch (err) {
        if (controller.signal.aborted) return
        const message = formatError(err)
        setFetchState({ status: 'error', message })
        addToast('error', t('fetch.failed', { message }))
      } finally {
        if (activeRequestRef.current === controller) {
          activeRequestRef.current = null
        }
      }
    },
    [urls, provider, timeout, canFetch, addToast, t],
  )

  const handleRetry = useCallback(() => {
    const syntheticEvent = { preventDefault: () => {} } as FormEvent
    handleFetch(syntheticEvent)
  }, [handleFetch])

  const toggleExpanded = (index: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      addToast('success', t('fetch.copied', 'Copied to clipboard'))
    } catch (err) {
      addToast('error', t('fetch.copyFailed', 'Failed to copy'))
    }
  }

  const downloadAsMarkdown = (item: FetchResult) => {
    const md = `# ${item.title || item.url}\n\n**URL:** ${item.final_url}\n\n${item.content || ''}`
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${item.title?.replace(/[^a-zA-Z0-9]/g, '_') || 'content'}.md`
    a.click()
    URL.revokeObjectURL(url)
    addToast('success', t('fetch.downloaded', 'Downloaded as Markdown'))
  }

  const exportAllAsMarkdown = () => {
    if (!results || results.results.length === 0) return
    const md = results.results
      .filter((item) => !item.error)
      .map((item) => `# ${item.title || item.url}\n\n**URL:** ${item.final_url}\n\n${item.content || ''}\n\n---\n`)
      .join('\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'all_content.md'
    a.click()
    URL.revokeObjectURL(url)
    addToast('success', t('fetch.allDownloaded', 'All content downloaded'))
  }

  const renderResults = () => {
    if (isLoading) {
      return (
        <div role="status" aria-live="polite" aria-busy="true">
          <div className={styles.fetchingHint}>{t('fetch.fetchingHint', 'Fetching content...')}</div>
          <ResultsSkeleton count={3} />
        </div>
      )
    }

    if (fetchState.status === 'error') {
      return (
        <EmptyState
          type="error"
          title={t('fetch.errorStateTitle', 'Fetch Failed')}
          description={fetchState.message}
          action={
            <button type="button" className="btn btn-primary btn-sm" onClick={handleRetry}>
              {t('fetch.retryFetch', 'Retry')}
            </button>
          }
        />
      )
    }

    if (!results) return null

    if (results.results.length === 0) {
      return <EmptyState type="search" title={t('fetch.noResults', 'No results')} />
    }

    return (
      <div>
        <div className={styles.resultsToolbar}>
          <div className={styles.resultStats}>
            <Badge color="green">{t('fetch.successful', { count: results.total_ok })}</Badge>
            <Badge color="red">{t('fetch.failedCount', { count: results.total_failed })}</Badge>
            <Badge color="blue">{results.provider}</Badge>
          </div>
          <button
            type="button"
            className={styles.exportBtn}
            onClick={exportAllAsMarkdown}
            title={t('fetch.exportAll', 'Export all as Markdown')}
          >
            <Download size={13} /> {t('fetch.exportAll', 'Export All')}
          </button>
        </div>

        <m.div variants={staggerContainer} initial="initial" animate="animate">
          {results.results.map((item, i) => {
            const isExpanded = expandedItems.has(i)
            const hasError = !!item.error
            const key = `${item.url}-${i}`

            return (
              <m.article key={key} className={styles.resultCard} variants={staggerItem}>
                <div className={styles.cardHeader}>
                  <div className={styles.cardHeaderLeft}>
                    {hasError ? (
                      <AlertCircle size={18} className={styles.errorIcon} />
                    ) : (
                      <CheckCircle2 size={18} className={styles.successIcon} />
                    )}
                    <h3 className={styles.resultTitle}>
                      {item.title || item.url}
                    </h3>
                  </div>
                  <Badge color={hasError ? 'red' : 'green'}>
                    {hasError ? 'Failed' : 'Success'}
                  </Badge>
                </div>

                <div className={styles.resultUrl}>
                  <Globe size={12} />
                  {isSafeUrl(item.final_url) ? (
                    <a href={item.final_url} target="_blank" rel="noopener noreferrer">
                      {item.final_url}
                      <ExternalLink size={12} className={styles.externalIcon} />
                    </a>
                  ) : (
                    <span>{item.final_url}</span>
                  )}
                </div>

                {hasError ? (
                  <div className={styles.errorMessage}>
                    <AlertCircle size={14} />
                    {item.error}
                  </div>
                ) : (
                  <>
                    {item.snippet && (
                      <p className={styles.resultSnippet}>{item.snippet}</p>
                    )}

                    {item.content && (
                      <>
                        <div className={styles.contentToggle}>
                          <button
                            type="button"
                            className={styles.toggleBtn}
                            onClick={() => toggleExpanded(i)}
                          >
                            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            {isExpanded
                              ? t('fetch.hideContent', 'Hide Content')
                              : t('fetch.showContent', 'Show Content')}
                          </button>
                          <div className={styles.contentActions}>
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title={t('fetch.copy', 'Copy')}
                            >
                              <Copy size={13} />
                            </button>
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title={t('fetch.download', 'Download')}
                            >
                              <Download size={13} />
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className={styles.fullContent}>
                            <pre>{item.content}</pre>
                          </div>
                        )}
                      </>
                    )}

                    {item.author && (
                      <div className={styles.metadata}>
                        <span>Author: {item.author}</span>
                      </div>
                    )}
                    {item.published_date && (
                      <div className={styles.metadata}>
                        <span>Published: {item.published_date}</span>
                      </div>
                    )}
                  </>
                )}
              </m.article>
            )
          })}
        </m.div>
      </div>
    )
  }

  const hasResults = results !== null

  return (
    <div className={styles.page}>
      {!hasResults && (
        <m.div className={styles.heroTitle} {...fadeInUp}>
          <h1 className={styles.heroHeading}>{t('fetch.heroTitle', 'Web Content Fetcher')}</h1>
          <p className={styles.heroSubtitle}>
            {t('fetch.heroSubtitle', 'Extract clean content from any webpage')}
          </p>
        </m.div>
      )}

      <m.div className={`${styles.commandCard} ${hasResults ? styles.compact : ''}`} {...fadeInUp}>
        <div className={styles.commandHeader}>
          <div className={styles.headerTitle}>
            <LinkIcon size={18} />
            <span>{t('fetch.title', 'Fetch Web Content')}</span>
          </div>
        </div>

        <m.form className={styles.fetchForm} onSubmit={handleFetch} aria-busy={isLoading}>
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="fetch-urls">
              {t('fetch.urlsLabel', 'URLs (one per line)')}
            </label>
            <div className={styles.textareaWrapper}>
              <Sparkles size={20} className={styles.inputIcon} />
              <textarea
                id="fetch-urls"
                ref={inputRef}
                className={styles.textarea}
                value={urls}
                onChange={(e) => setUrls(e.target.value)}
                placeholder={t('fetch.urlsPlaceholder', 'https://example.com\nhttps://another.com')}
                rows={6}
                required
              />
            </div>
            <div className={styles.urlCount}>
              {t('fetch.validUrls', { count: parseUrls(urls).length })}
            </div>
          </div>

          <div className={styles.controlsRow}>
            <div className={styles.providerGroup}>
              <label className={styles.label} htmlFor="fetch-provider">{t('fetch.provider', 'Provider')}</label>
              <select
                id="fetch-provider"
                className={styles.select}
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              className={styles.fetchButton}
              disabled={!canFetch || isLoading}
              aria-label={t('fetch.button', 'Fetch')}
            >
              {isLoading ? t('fetch.fetching', 'Fetching...') : t('fetch.button', 'Fetch')}
            </button>
          </div>
        </m.form>

        <div className={styles.advancedToggle}>
          <button
            type="button"
            className={styles.advancedToggleBtn}
            onClick={() => setShowAdvanced((v) => !v)}
          >
            <Settings size={14} />
            {t('advancedSearch.title', 'Advanced')}
          </button>
        </div>

        {showAdvanced && (
          <div className={styles.advancedPanel}>
            <div className={styles.advancedField}>
              <label className={styles.advancedLabel} htmlFor="fetch-timeout">
                {t('fetch.timeout', 'Timeout')}: <strong>{timeout}s</strong>
              </label>
              <input
                id="fetch-timeout"
                type="range"
                min={5}
                max={120}
                value={timeout}
                onChange={(e) => setTimeout_(Number(e.target.value))}
                className={styles.slider}
              />
              <div className={styles.rangeHint}>
                {t('fetch.timeoutHint', '5-120 seconds')}
              </div>
            </div>
            <button
              type="button"
              className={styles.resetBtn}
              onClick={() => setTimeout_(30)}
            >
              {t('advancedSearch.reset', 'Reset')}
            </button>
          </div>
        )}
      </m.div>

      <div className={styles.results} aria-live="polite">
        {renderResults()}
      </div>
    </div>
  )
}
