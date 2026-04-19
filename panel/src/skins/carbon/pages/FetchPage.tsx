/**
 * 网页抓取页面 - Carbon 皮肤版本
 *
 * 文件用途：提供网页内容抓取界面，支持多 URL 输入、多种抓取提供商、结果展示和导出
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Globe, ExternalLink, Copy, Download, CheckCircle2,
  AlertCircle, ChevronDown, ChevronUp, Terminal,
  Settings, Link as LinkIcon,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import type { FetchResponse, FetchResult } from '@core/types'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

type Provider = 'builtin' | 'jina_reader' | 'tavily' | 'firecrawl' | 'exa'

const PROVIDERS: { value: Provider; label: string; description: string }[] = [
  { value: 'builtin', label: 'BUILTIN', description: 'Built-in fetcher' },
  { value: 'jina_reader', label: 'JINA_READER', description: 'Jina.ai Reader API' },
  { value: 'tavily', label: 'TAVILY', description: 'Tavily Extract API' },
  { value: 'firecrawl', label: 'FIRECRAWL', description: 'Firecrawl service' },
  { value: 'exa', label: 'EXA', description: 'Exa.ai API' },
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
        <div className={styles.loadingState}>
          <Terminal size={24} className={styles.loadingIcon} />
          <div className={styles.loadingText}>{t('fetch.fetchingHint', 'FETCHING_CONTENT...')}</div>
        </div>
      )
    }

    if (fetchState.status === 'error') {
      return (
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <div className={styles.errorTitle}>{t('fetch.errorStateTitle', 'FETCH_FAILED')}</div>
          <div className={styles.errorMessage}>{fetchState.message}</div>
          <button type="button" className={styles.retryBtn} onClick={handleRetry}>
            {t('fetch.retryFetch', 'RETRY')}
          </button>
        </div>
      )
    }

    if (!results) return null

    if (results.results.length === 0) {
      return (
        <div className={styles.emptyState}>
          <Globe size={48} />
          <div className={styles.emptyText}>{t('fetch.noResults', 'NO_RESULTS')}</div>
        </div>
      )
    }

    return (
      <div>
        <div className={styles.resultsHeader}>
          <div className={styles.stats}>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>OK:</span>
              <span className={styles.statValue}>{results.total_ok}</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>FAILED:</span>
              <span className={styles.statValue}>{results.total_failed}</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>PROVIDER:</span>
              <span className={styles.statValue}>{results.provider.toUpperCase()}</span>
            </div>
          </div>
          <button
            type="button"
            className={styles.exportAllBtn}
            onClick={exportAllAsMarkdown}
          >
            <Download size={14} />
            {t('fetch.exportAll', 'EXPORT_ALL')}
          </button>
        </div>

        <m.div className={styles.resultsList} variants={staggerContainer} initial="initial" animate="animate">
          {results.results.map((item, i) => {
            const isExpanded = expandedItems.has(i)
            const hasError = !!item.error
            const key = `${item.url}-${i}`

            return (
              <m.div key={key} className={styles.resultItem} variants={staggerItem}>
                <div className={styles.resultHeader}>
                  <div className={styles.resultStatus}>
                    {hasError ? (
                      <AlertCircle size={16} className={styles.statusIconError} />
                    ) : (
                      <CheckCircle2 size={16} className={styles.statusIconSuccess} />
                    )}
                    <span className={styles.statusText}>
                      {hasError ? 'FAILED' : 'SUCCESS'}
                    </span>
                  </div>
                  <div className={styles.resultTitle}>
                    {item.title || item.url}
                  </div>
                </div>

                <div className={styles.resultUrl}>
                  <Globe size={12} />
                  <a href={item.final_url} target="_blank" rel="noopener noreferrer">
                    {item.final_url}
                    <ExternalLink size={12} />
                  </a>
                </div>

                {hasError ? (
                  <div className={styles.errorBox}>
                    <AlertCircle size={14} />
                    <span>{item.error}</span>
                  </div>
                ) : (
                  <>
                    {item.snippet && (
                      <div className={styles.snippet}>{item.snippet}</div>
                    )}

                    {item.content && (
                      <div className={styles.contentSection}>
                        <div className={styles.contentControls}>
                          <button
                            type="button"
                            className={styles.toggleContentBtn}
                            onClick={() => toggleExpanded(i)}
                          >
                            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            {isExpanded ? 'HIDE_CONTENT' : 'SHOW_CONTENT'}
                          </button>
                          <div className={styles.contentActions}>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title="COPY"
                            >
                              <Copy size={14} />
                            </button>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title="DOWNLOAD"
                            >
                              <Download size={14} />
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className={styles.contentBox}>
                            <pre>{item.content}</pre>
                          </div>
                        )}
                      </div>
                    )}

                    {(item.author || item.published_date) && (
                      <div className={styles.meta}>
                        {item.author && <span>AUTHOR: {item.author}</span>}
                        {item.published_date && <span>PUBLISHED: {item.published_date}</span>}
                      </div>
                    )}
                  </>
                )}
              </m.div>
            )
          })}
        </m.div>
      </div>
    )
  }

  const hasResults = results !== null

  return (
    <div className={styles.page}>
      <div className={styles.gridOverlay} />

      {!hasResults && (
        <m.div className={styles.hero} {...fadeInUp}>
          <h1 className={styles.heroTitle}>FETCH_CONTENT</h1>
          <div className={styles.heroSubtitle}>
            <Terminal size={14} />
            {t('fetch.heroSubtitle', 'EXTRACT_CLEAN_WEB_CONTENT')}
          </div>
        </m.div>
      )}

      <m.div className={`${styles.panel} ${hasResults ? styles.compact : ''}`} {...fadeInUp}>
        <div className={styles.panelHeader}>
          <LinkIcon size={16} />
          <span>{t('fetch.title', 'WEB_CONTENT_FETCHER')}</span>
        </div>

        <form className={styles.form} onSubmit={handleFetch}>
          <div className={styles.field}>
            <label className={styles.fieldLabel}>
              {t('fetch.urlsLabel', 'URLS')} <span className={styles.hint}>(one per line)</span>
            </label>
            <textarea
              ref={inputRef}
              className={styles.textarea}
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              placeholder="https://example.com&#10;https://another.com"
              rows={6}
              required
            />
            <div className={styles.urlCount}>
              {parseUrls(urls).length} {t('fetch.validUrls', 'valid URLs')}
            </div>
          </div>

          <div className={styles.controlRow}>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>{t('fetch.provider', 'PROVIDER')}</label>
              <select
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
              className={styles.submitBtn}
              disabled={!canFetch}
            >
              {isLoading ? 'FETCHING...' : 'FETCH'}
            </button>
          </div>
        </form>

        <div className={styles.advancedToggle}>
          <button
            type="button"
            className={styles.advancedBtn}
            onClick={() => setShowAdvanced((v) => !v)}
          >
            <Settings size={12} />
            {t('advancedSearch.title', 'ADVANCED')}
          </button>
        </div>

        {showAdvanced && (
          <div className={styles.advancedPanel}>
            <div className={styles.field}>
              <label className={styles.fieldLabel}>
                {t('fetch.timeout', 'TIMEOUT')}: {timeout}s
              </label>
              <input
                type="range"
                min={5}
                max={120}
                value={timeout}
                onChange={(e) => setTimeout_(Number(e.target.value))}
                className={styles.slider}
              />
              <div className={styles.hint}>5-120 seconds</div>
            </div>
            <button
              type="button"
              className={styles.resetBtn}
              onClick={() => setTimeout_(30)}
            >
              RESET
            </button>
          </div>
        )}
      </m.div>

      <div className={styles.results}>
        {renderResults()}
      </div>
    </div>
  )
}
