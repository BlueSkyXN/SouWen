/**
 * 网页抓取页面 - Classic 皮肤版本
 *
 * 文件用途：提供网页内容抓取界面，支持多 URL 输入、多种抓取提供商、结果展示和导出
 *
 * 业务逻辑统一抽取至 `@core/hooks/useFetchPage`，本文件仅保留 Classic 皮肤特有的 UI 渲染。
 */

import { m } from 'framer-motion'
import {
  Globe, ExternalLink, Copy, Download, CheckCircle2,
  AlertCircle, ChevronDown, ChevronUp, Sparkles,
  Settings, Link as LinkIcon,
} from 'lucide-react'
import { useFetchPage, isSafeUrl, type Provider } from '@core/hooks/useFetchPage'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { Badge } from '../components/common/Badge'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

const PROVIDERS: { value: Provider; label: string; description: string }[] = [
  { value: 'builtin', label: 'Builtin', description: 'Built-in fetcher (default)' },
  { value: 'jina_reader', label: 'Jina Reader', description: 'Jina.ai Reader API' },
  { value: 'tavily', label: 'Tavily', description: 'Tavily Extract API' },
  { value: 'firecrawl', label: 'Firecrawl', description: 'Firecrawl scraping service' },
  { value: 'exa', label: 'Exa', description: 'Exa.ai content API' },
  { value: 'crawl4ai', label: 'Crawl4AI', description: 'Headless browser (local)' },
  { value: 'scrapfly', label: 'Scrapfly', description: 'JS rendering + AI extraction' },
  { value: 'diffbot', label: 'Diffbot', description: 'Structured article extraction' },
  { value: 'scrapingbee', label: 'ScrapingBee', description: 'Proxy + JS rendering + anti-bot' },
  { value: 'zenrows', label: 'ZenRows', description: 'Proxy + JS rendering + anti-bot' },
  { value: 'scraperapi', label: 'ScraperAPI', description: 'Proxy pool + JS rendering' },
  { value: 'apify', label: 'Apify', description: 'Actor-based web crawler platform' },
  { value: 'cloudflare', label: 'Cloudflare', description: 'Edge browser rendering (markdown)' },
  { value: 'wayback', label: 'Wayback Machine', description: 'Internet Archive cached pages (free)' },
  { value: 'newspaper', label: 'Newspaper', description: 'News article extraction (local)' },
  { value: 'readability', label: 'Readability', description: 'Mozilla Readability algorithm (local)' },
  { value: 'mcp', label: 'MCP', description: 'MCP protocol content fetch (external tool)' },
  { value: 'site_crawler', label: 'SiteCrawler', description: 'BFS site crawler (multi-page batch)' },
  { value: 'deepwiki', label: 'DeepWiki', description: 'Open-source project docs (free)' },
]

export function FetchPage() {
  const {
    t,
    urls, setUrls,
    provider, setProvider,
    timeout, setTimeout_,
    showAdvanced, setShowAdvanced,
    selector, setSelector,
    respectRobots, setRespectRobots,
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
              {t('fetch.validUrls', { count: validUrls.length })}
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
            {provider === 'builtin' && (
              <div className={styles.advancedField}>
                <label className={styles.advancedLabel} htmlFor="fetch-selector">
                  {t('fetch.selector', 'CSS Selector')}
                </label>
                <input
                  id="fetch-selector"
                  type="text"
                  className={styles.input}
                  value={selector}
                  onChange={(e) => setSelector(e.target.value)}
                  placeholder={t('fetch.selectorPlaceholder', 'e.g. article, .content, #main')}
                  disabled={isLoading}
                />
              </div>
            )}
            {provider === 'builtin' && (
              <div className={styles.advancedField}>
                <label className={styles.toggleField}>
                  <span className={styles.toggleSwitch}>
                    <input
                      type="checkbox"
                      className={styles.toggleInput}
                      checked={respectRobots}
                      onChange={(e) => setRespectRobots(e.target.checked)}
                      disabled={isLoading}
                    />
                    <span className={styles.toggleSlider} />
                  </span>
                  <span>{t('fetch.respectRobots', 'Respect robots.txt')}</span>
                </label>
              </div>
            )}
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
