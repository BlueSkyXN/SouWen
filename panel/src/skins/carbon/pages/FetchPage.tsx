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
import { useFetchPage, isSafeUrl, type FetchStrategy, type Provider } from '@core/hooks/useFetchPage'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

export function FetchPage() {
  const {
    t,
    urls, setUrls,
    provider, setProvider,
    providerOptions,
    selectedProviders, toggleProvider,
    strategy, setStrategy,
    timeout, setTimeout_,
    showAdvanced, setShowAdvanced,
    selector, setSelector,
    startIndex, setStartIndex,
    maxLength, setMaxLength,
    respectRobots, setRespectRobots,
    supportsExtractOptions,
    resetAdvancedOptions,
    fetchState,
    results,
    providerSummary,
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
          <div className={styles.loadingText}>{t('fetch.fetchingHint')}</div>
        </div>
      )
    }

    if (fetchState.status === 'error') {
      return (
        <div className={styles.errorState}>
          <AlertCircle size={48} />
          <div className={styles.errorTitle}>{t('fetch.errorStateTitle')}</div>
          <div className={styles.errorMessage}>{fetchState.message}</div>
          <button type="button" className={styles.retryBtn} onClick={handleRetry}>
            {t('fetch.retryFetch')}
          </button>
        </div>
      )
    }

    if (!results) return null

    if (results.results.length === 0) {
      return (
        <div className={styles.emptyState}>
          <Globe size={48} />
          <div className={styles.emptyText}>{t('fetch.noResults')}</div>
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
              <span className={styles.statValue}>{providerSummary.toUpperCase()}</span>
            </div>
          </div>
          <button
            type="button"
            className={styles.exportAllBtn}
            onClick={exportAllAsMarkdown}
          >
            <Download size={14} />
            {t('fetch.exportAll')}
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
                      {hasError ? t('fetch.statusFailed') : t('fetch.statusSuccess')}
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
                            {isExpanded ? t('fetch.hideContent') : t('fetch.showContent')}
                          </button>
                          <div className={styles.contentActions}>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title={t('fetch.copy')}
                            >
                              <Copy size={14} />
                            </button>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title={t('fetch.download')}
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

                    {(item.author || item.published_date || (
                      item.content_truncated && item.next_start_index !== null && item.next_start_index !== undefined
                    )) && (
                      <div className={styles.meta}>
                        {item.author && <span>{t('fetch.author')}: {item.author}</span>}
                        {item.published_date && <span>{t('fetch.published')}: {item.published_date}</span>}
                        {item.content_truncated && item.next_start_index !== null && item.next_start_index !== undefined && (
                          <span>
                            {t('fetch.truncatedAt', {
                              index: item.next_start_index,
                              defaultValue: 'TRUNCATED, NEXT SEGMENT STARTS AT {{index}}',
                            })}
                          </span>
                        )}
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
            {t('fetch.heroSubtitle')}
          </div>
        </m.div>
      )}

      <m.div className={`${styles.panel} ${hasResults ? styles.compact : ''}`} {...fadeInUp}>
        <div className={styles.panelHeader}>
          <LinkIcon size={16} />
          <span>{t('fetch.title')}</span>
        </div>

        <form className={styles.form} onSubmit={handleFetch}>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="fetch-urls">
              {t('fetch.urlsLabel')}
            </label>
            <textarea
              id="fetch-urls"
              ref={inputRef}
              className={styles.textarea}
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              placeholder={t('fetch.urlsPlaceholder')}
              rows={6}
              required
            />
            <div className={styles.urlCount}>
              {t('fetch.validUrls', { count: validUrls.length })}
            </div>
          </div>

          <div className={styles.controlRow}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-provider">{t('fetch.provider')}</label>
              <select
                id="fetch-provider"
                className={styles.select}
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
              >
                {providerOptions.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={!canFetch || isLoading}
            >
              {isLoading ? t('fetch.fetching') : t('fetch.button')}
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
            {t('advancedSearch.title')}
          </button>
        </div>

        {showAdvanced && (
          <div className={styles.advancedPanel}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-timeout">
                {t('fetch.timeout')}: {timeout}s
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
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-strategy">
                {t('fetch.strategy')}
              </label>
              <select
                id="fetch-strategy"
                className={styles.select}
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as FetchStrategy)}
                disabled={isLoading}
              >
                <option value="fallback">{t('fetch.strategyFallback')}</option>
                <option value="fanout">{t('fetch.strategyFanout')}</option>
              </select>
            </div>
            <div className={styles.field}>
              <span className={styles.fieldLabel}>{t('fetch.providers')}</span>
              <div className={styles.providerChecklist}>
                {providerOptions.map((item) => (
                  <label key={item.value} className={styles.providerCheck}>
                    <input
                      type="checkbox"
                      checked={selectedProviders.includes(item.value)}
                      onChange={() => toggleProvider(item.value)}
                      disabled={isLoading || (selectedProviders.length === 1 && selectedProviders.includes(item.value))}
                    />
                    <span>{item.label.toUpperCase()}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-start-index">
                {t('fetch.startIndex')}
              </label>
              <input
                id="fetch-start-index"
                type="number"
                min={0}
                step={1}
                value={startIndex}
                onChange={(e) => setStartIndex(Math.max(0, Number(e.target.value) || 0))}
                disabled={isLoading}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="fetch-max-length">
                {t('fetch.maxLength')}
              </label>
              <input
                id="fetch-max-length"
                type="number"
                min={0}
                step={1}
                value={maxLength ?? ''}
                onChange={(e) => {
                  const value = e.target.value
                  setMaxLength(value === '' ? undefined : Math.max(0, Number(value) || 0))
                }}
                disabled={isLoading}
              />
            </div>
            {supportsExtractOptions && (
              <div className={styles.field}>
                <label className={styles.fieldLabel} htmlFor="fetch-selector">
                  {t('fetch.selector')}
                </label>
                <input
                  id="fetch-selector"
                  type="text"
                  value={selector}
                  onChange={(e) => setSelector(e.target.value)}
                  placeholder={t('fetch.selectorPlaceholder')}
                  disabled={isLoading}
                />
              </div>
            )}
            {supportsExtractOptions && (
              <div className={styles.field}>
                <label className={styles.fieldLabel}>
                  <input
                    type="checkbox"
                    checked={respectRobots}
                    onChange={(e) => setRespectRobots(e.target.checked)}
                    disabled={isLoading}
                  />
                  {' '}{t('fetch.respectRobots')}
                </label>
              </div>
            )}
            <button
              type="button"
              className={styles.resetBtn}
              onClick={resetAdvancedOptions}
            >
              {t('advancedSearch.reset')}
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
