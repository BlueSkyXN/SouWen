/**
 * 网页抓取页面 - iOS 皮肤版本
 *
 * 文件用途：提供网页内容抓取界面，支持多 URL 输入、多种抓取提供商、结果展示和导出
 *
 * 业务逻辑统一抽取至 `@core/hooks/useFetchPage`，本文件仅保留 iOS 皮肤特有的 UI 渲染。
 */

import { m } from 'framer-motion'
import {
  Globe, ExternalLink, Copy, Download, CheckCircle2,
  AlertCircle, ChevronDown, ChevronUp, Search,
  Settings,
} from 'lucide-react'
import { useFetchPage, isSafeUrl, type Provider } from '@core/hooks/useFetchPage'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

const PROVIDERS: { value: Provider; label: string }[] = [
  { value: 'builtin', label: 'Builtin' },
  { value: 'jina_reader', label: 'Jina Reader' },
  { value: 'tavily', label: 'Tavily' },
  { value: 'firecrawl', label: 'Firecrawl' },
  { value: 'exa', label: 'Exa' },
  { value: 'crawl4ai', label: 'Crawl4AI' },
  { value: 'scrapfly', label: 'Scrapfly' },
  { value: 'diffbot', label: 'Diffbot' },
  { value: 'scrapingbee', label: 'ScrapingBee' },
  { value: 'zenrows', label: 'ZenRows' },
  { value: 'scraperapi', label: 'ScraperAPI' },
  { value: 'apify', label: 'Apify' },
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
          <div className={styles.spinner} />
          <div className={styles.loadingText}>{t('fetch.fetchingHint', 'Fetching content...')}</div>
        </div>
      )
    }

    if (fetchState.status === 'error') {
      return (
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <div className={styles.errorTitle}>{t('fetch.errorStateTitle', 'Fetch Failed')}</div>
          <div className={styles.errorMessage}>{fetchState.message}</div>
          <button type="button" className={styles.retryBtn} onClick={handleRetry}>
            {t('fetch.retryFetch', 'Try Again')}
          </button>
        </div>
      )
    }

    if (!results) return null

    if (results.results.length === 0) {
      return (
        <div className={styles.emptyState}>
          <Globe size={48} />
          <div className={styles.emptyText}>{t('fetch.noResults', 'No results')}</div>
        </div>
      )
    }

    return (
      <div>
        <div className={styles.resultsHeader}>
          <div className={styles.stats}>
            <span className={styles.statBadge}>{t('fetch.successfulCount', { count: results.total_ok })}</span>
            <span className={styles.statBadge}>{t('fetch.failedCount', { count: results.total_failed })}</span>
            <span className={styles.statBadge}>{results.provider}</span>
          </div>
          <button
            type="button"
            className={styles.exportBtn}
            onClick={exportAllAsMarkdown}
          >
            <Download size={14} />
            {t('fetch.exportAll', 'Export All')}
          </button>
        </div>

        <m.div className={styles.resultsList} variants={staggerContainer} initial="initial" animate="animate">
          {results.results.map((item, i) => {
            const isExpanded = expandedItems.has(i)
            const hasError = !!item.error
            const key = `${item.url}-${i}`

            return (
              <m.div key={key} className={styles.resultCard} variants={staggerItem}>
                <div className={styles.cardHeader}>
                  <div className={styles.headerLeft}>
                    {hasError ? (
                      <AlertCircle size={18} className={styles.errorIcon} />
                    ) : (
                      <CheckCircle2 size={18} className={styles.successIcon} />
                    )}
                    <h3 className={styles.cardTitle}>{item.title || item.url}</h3>
                  </div>
                  <span className={hasError ? styles.badgeError : styles.badgeSuccess}>
                    {hasError ? t('fetch.statusFailed', 'Failed') : t('fetch.statusSuccess', 'Success')}
                  </span>
                </div>

                <div className={styles.cardUrl}>
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
                    {item.error}
                  </div>
                ) : (
                  <>
                    {item.snippet && (
                      <p className={styles.snippet}>{item.snippet}</p>
                    )}

                    {item.content && (
                      <>
                        <div className={styles.contentControls}>
                          <button
                            type="button"
                            className={styles.toggleBtn}
                            onClick={() => toggleExpanded(i)}
                          >
                            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            {isExpanded ? t('fetch.hideContent', 'Hide Content') : t('fetch.showContent', 'Show Content')}
                          </button>
                          <div className={styles.actions}>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title={t('fetch.copy', 'Copy')}
                            >
                              <Copy size={13} />
                            </button>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title={t('fetch.download', 'Download')}
                            >
                              <Download size={13} />
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className={styles.contentBox}>
                            <pre>{item.content}</pre>
                          </div>
                        )}
                      </>
                    )}

                    {(item.author || item.published_date) && (
                      <div className={styles.metadata}>
                        {item.author && <span>{t('fetch.author', 'Author')}: {item.author}</span>}
                        {item.published_date && <span>{t('fetch.published', 'Published')}: {item.published_date}</span>}
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
      {!hasResults && (
        <m.div className={styles.hero} {...fadeInUp}>
          <h1 className={styles.heroTitle}>{t('fetch.heroTitle', 'Web Content Fetcher')}</h1>
          <div className={styles.heroSubtitle}>
            <Search size={18} />
            {t('fetch.heroSubtitle', 'Extract clean content from any webpage')}
          </div>
        </m.div>
      )}

      <m.div className={styles.panel} {...fadeInUp}>
        <form className={styles.form} onSubmit={handleFetch}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="fetch-urls">
              {t('fetch.urlsLabel', 'URLs')} <span className={styles.hint}>(one per line)</span>
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
            <div className={styles.providerField}>
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
              className={styles.submitBtn}
              disabled={!canFetch || isLoading}
            >
              {isLoading ? t('fetch.fetching', 'Fetching...') : t('fetch.button', 'Fetch')}
            </button>
          </div>

          <button
            type="button"
            className={styles.advancedToggle}
            onClick={() => setShowAdvanced((v) => !v)}
          >
            <Settings size={14} />
            {t('advancedSearch.title', 'Advanced')}
          </button>

          {showAdvanced && (
            <div className={styles.advancedPanel}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="fetch-timeout">
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
                <div className={styles.hint}>{t('fetch.timeoutHint', '5-120 seconds')}</div>
              </div>
              <button
                type="button"
                className={styles.resetBtn}
                onClick={() => setTimeout_(30)}
              >
                {t('advancedSearch.reset', 'Reset to Default')}
              </button>
            </div>
          )}
        </form>
      </m.div>

      <div className={styles.results}>
        {renderResults()}
      </div>
    </div>
  )
}
