/**
 * 网页抓取页面 - Carbon 皮肤版本
 *
 * 文件用途：提供网页内容抓取界面，支持多 URL 输入、多种抓取提供商、结果展示和导出
 *
 * 业务逻辑统一抽取至 `@core/hooks/useFetchPage`，本文件仅保留 Carbon 皮肤特有的 UI 渲染。
 */

import { m } from 'framer-motion'
import {
  Globe, ExternalLink, Copy, Download, CheckCircle2,
  AlertCircle, ChevronDown, ChevronUp, Terminal,
  Settings, Link as LinkIcon,
} from 'lucide-react'
import { useFetchPage, isSafeUrl, type Provider } from '@core/hooks/useFetchPage'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

const PROVIDERS: { value: Provider; label: string; description: string }[] = [
  { value: 'builtin', label: 'BUILTIN', description: 'Built-in fetcher' },
  { value: 'jina_reader', label: 'JINA_READER', description: 'Jina.ai Reader API' },
  { value: 'tavily', label: 'TAVILY', description: 'Tavily Extract API' },
  { value: 'firecrawl', label: 'FIRECRAWL', description: 'Firecrawl service' },
  { value: 'exa', label: 'EXA', description: 'Exa.ai API' },
  { value: 'crawl4ai', label: 'CRAWL4AI', description: 'Headless browser' },
  { value: 'scrapfly', label: 'SCRAPFLY', description: 'JS + AI extraction' },
  { value: 'diffbot', label: 'DIFFBOT', description: 'Article extraction' },
  { value: 'scrapingbee', label: 'SCRAPINGBEE', description: 'Proxy + JS rendering' },
  { value: 'zenrows', label: 'ZENROWS', description: 'Proxy + JS rendering' },
  { value: 'scraperapi', label: 'SCRAPERAPI', description: 'Proxy pool + JS' },
  { value: 'apify', label: 'APIFY', description: 'Actor crawler platform' },
  { value: 'cloudflare', label: 'CLOUDFLARE', description: 'Edge browser rendering' },
  { value: 'wayback', label: 'WAYBACK', description: 'Archive cached pages' },
  { value: 'newspaper', label: 'NEWSPAPER', description: 'News extraction (local)' },
  { value: 'readability', label: 'READABILITY', description: 'Mozilla algo (local)' },
]

export function FetchPage() {
  const {
    t,
    urls, setUrls,
    provider, setProvider,
    timeout, setTimeout_,
    showAdvanced, setShowAdvanced,
    fetchState,
    results,
    expandedItems,
    inputRef,
    validUrls,
    canFetch,
    isLoading,
    hasResults,
    handleFetch,
    handleRetry,
    toggleExpanded,
    copyToClipboard,
    downloadAsMarkdown,
    exportAllAsMarkdown,
  } = useFetchPage()

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
                      {hasError ? t('fetch.statusFailed', 'FAILED') : t('fetch.statusSuccess', 'SUCCESS')}
                    </span>
                  </div>
                  <div className={styles.resultTitle}>
                    {item.title || item.url}
                  </div>
                </div>

                <div className={styles.resultUrl}>
                  <Globe size={12} />
                  {isSafeUrl(item.final_url) ? (
                    <a href={item.final_url} target="_blank" rel="noopener noreferrer">
                      {item.final_url}
                      <ExternalLink size={12} />
                    </a>
                  ) : (
                    <span>{item.final_url}</span>
                  )}
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
                            {isExpanded ? t('fetch.hideContent', 'HIDE_CONTENT') : t('fetch.showContent', 'SHOW_CONTENT')}
                          </button>
                          <div className={styles.contentActions}>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title={t('fetch.copy', 'COPY')}
                            >
                              <Copy size={14} />
                            </button>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title={t('fetch.download', 'DOWNLOAD')}
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
                        {item.author && <span>{t('fetch.author', 'AUTHOR')}: {item.author}</span>}
                        {item.published_date && <span>{t('fetch.published', 'PUBLISHED')}: {item.published_date}</span>}
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
            <label className={styles.fieldLabel} htmlFor="fetch-urls">
              {t('fetch.urlsLabel', 'URLS')} <span className={styles.hint}>(one per line)</span>
            </label>
            <textarea
              id="fetch-urls"
              ref={inputRef}
              className={styles.textarea}
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              placeholder="https://example.com&#10;https://another.com"
              rows={6}
              required
            />
            <div className={styles.urlCount}>
              {t('fetch.validUrls', { count: validUrls.length })}
            </div>
          </div>

          <div className={styles.controlRow}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-provider">{t('fetch.provider', 'PROVIDER')}</label>
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
              className={styles.submitBtn}
              disabled={!canFetch || isLoading}
            >
              {isLoading ? t('fetch.fetching', 'FETCHING...') : t('fetch.button', 'FETCH')}
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
              <label className={styles.fieldLabel} htmlFor="fetch-timeout">
                {t('fetch.timeout', 'TIMEOUT')}: {timeout}s
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
              <div className={styles.hint}>5-120 seconds</div>
            </div>
            <button
              type="button"
              className={styles.resetBtn}
              onClick={() => setTimeout_(30)}
            >
              {t('advancedSearch.reset', 'RESET')}
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
