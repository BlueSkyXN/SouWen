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
import { useFetchPage, isSafeUrl, type FetchStrategy, type Provider } from '@core/hooks/useFetchPage'
import { ResultsSkeleton } from '../components/common/Skeleton'
import { EmptyState } from '../components/common/EmptyState'
import { Badge } from '../components/common/Badge'
import { staggerContainer, staggerItem, fadeInUp } from '@core/lib/animations'
import styles from './FetchPage.module.scss'

export function FetchPage() {
  const {
    t,
    urls, setUrls,
    provider, setProvider,
    providerOptions, providerState,
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
        <div role="status" aria-live="polite" aria-busy="true">
          <div className={styles.fetchingHint}>{t('fetch.fetchingHint')}</div>
          <ResultsSkeleton count={3} />
        </div>
      )
    }

    if (fetchState.status === 'error') {
      return (
        <EmptyState
          type="error"
          title={t('fetch.errorStateTitle')}
          description={fetchState.message}
          action={
            <button type="button" className="btn btn-primary btn-sm" onClick={handleRetry}>
              {t('fetch.retryFetch')}
            </button>
          }
        />
      )
    }

    if (!results) return null

    if (results.results.length === 0) {
      return <EmptyState type="search" title={t('fetch.noResults')} />
    }

    return (
      <div>
        <div className={styles.resultsToolbar}>
          <div className={styles.resultStats}>
            <Badge color="green">{t('fetch.successful', { count: results.total_ok })}</Badge>
            <Badge color="red">{t('fetch.failedCount', { count: results.total_failed })}</Badge>
            <Badge color="blue">{providerSummary}</Badge>
          </div>
          <button
            type="button"
            className={styles.exportBtn}
            onClick={exportAllAsMarkdown}
            title={t('fetch.exportAll')}
          >
            <Download size={13} /> {t('fetch.exportAll')}
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
                              ? t('fetch.hideContent')
                              : t('fetch.showContent')}
                          </button>
                          <div className={styles.contentActions}>
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => copyToClipboard(item.content || '')}
                              title={t('fetch.copy')}
                            >
                              <Copy size={13} />
                            </button>
                            <button
                              type="button"
                              className={styles.actionBtn}
                              onClick={() => downloadAsMarkdown(item)}
                              title={t('fetch.download')}
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

                    {(item.author || item.published_date || (
                      item.content_truncated && item.next_start_index !== null && item.next_start_index !== undefined
                    )) && (
                      <div className={styles.metadata}>
                        {item.author && <span>{t('fetch.author')}: {item.author}</span>}
                        {item.published_date && <span>{t('fetch.published')}: {item.published_date}</span>}
                        {item.content_truncated && item.next_start_index !== null && item.next_start_index !== undefined && (
                          <span>
                            {t('fetch.truncatedAt', {
                              index: item.next_start_index,
                              defaultValue: 'Truncated, next segment starts at {{index}}',
                            })}
                          </span>
                        )}
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
          <h1 className={styles.heroHeading}>{t('fetch.heroTitle')}</h1>
          <p className={styles.heroSubtitle}>
            {t('fetch.heroSubtitle')}
          </p>
        </m.div>
      )}

      <m.div className={`${styles.commandCard} ${hasResults ? styles.compact : ''}`} {...fadeInUp}>
        <div className={styles.commandHeader}>
          <div className={styles.headerTitle}>
            <LinkIcon size={18} />
            <span>{t('fetch.title')}</span>
          </div>
        </div>

        <m.form className={styles.fetchForm} onSubmit={handleFetch} aria-busy={isLoading}>
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="fetch-urls">
              {t('fetch.urlsLabel')}
            </label>
            <div className={styles.textareaWrapper}>
              <Sparkles size={20} className={styles.inputIcon} />
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
            </div>
            <div className={styles.urlCount}>
              {t('fetch.validUrls', { count: validUrls.length })}
            </div>
          </div>

          <div className={styles.controlsRow}>
            <div className={styles.providerGroup}>
              <label className={styles.label} htmlFor="fetch-provider">{t('fetch.provider')}</label>
              <select
                id="fetch-provider"
                className={styles.select}
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
                disabled={isLoading || !providerOptions.some((item) => item.available)}
                aria-describedby="fetch-provider-status"
              >
                {!provider && <option value="">{providerState.message}</option>}
                {providerOptions.map((p) => (
                  <option key={p.value} value={p.value} disabled={!p.available}>
                    {p.label} — {p.statusLabel}
                  </option>
                ))}
              </select>
              <div id="fetch-provider-status" className={styles.rangeHint} role="status">
                {providerState.message}
              </div>
            </div>

            <button
              type="submit"
              className={styles.fetchButton}
              disabled={!canFetch || isLoading}
              aria-label={t('fetch.button')}
            >
              {isLoading ? t('fetch.fetching') : t('fetch.button')}
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
            {t('advancedSearch.title')}
          </button>
        </div>

        {showAdvanced && (
          <div className={styles.advancedPanel}>
            <div className={styles.advancedField}>
              <label className={styles.advancedLabel} htmlFor="fetch-timeout">
                {t('fetch.timeout')}: <strong>{timeout}s</strong>
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
                {t('fetch.timeoutHint')}
              </div>
            </div>
            <div className={styles.advancedField}>
              <label className={styles.advancedLabel} htmlFor="fetch-strategy">
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
            <div className={styles.advancedField}>
              <span className={styles.advancedLabel}>{t('fetch.providers')}</span>
              <div className={styles.providerChecklist}>
                {providerOptions.map((item) => (
                  <label key={item.value} className={styles.providerCheck} title={item.statusMessage}>
                    <input
                      type="checkbox"
                      checked={selectedProviders.includes(item.value)}
                      onChange={() => toggleProvider(item.value)}
                      disabled={
                        isLoading
                        || !item.available
                        || (selectedProviders.length === 1 && selectedProviders.includes(item.value))
                      }
                    />
                    <span>{item.label} · {item.statusLabel}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className={styles.advancedField}>
              <label className={styles.advancedLabel} htmlFor="fetch-start-index">
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
            <div className={styles.advancedField}>
              <label className={styles.advancedLabel} htmlFor="fetch-max-length">
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
              <div className={styles.advancedField}>
                <label className={styles.advancedLabel} htmlFor="fetch-selector">
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
              <div className={styles.advancedField}>
                <label className={styles.advancedLabel}>
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

      <div className={styles.results} aria-live="polite">
        {renderResults()}
      </div>
    </div>
  )
}
