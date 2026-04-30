/**
 * 工具箱页面 - iOS 皮肤版本
 *
 * 文件用途：Wayback Machine 网页归档查询与存档工具集合
 *
 * 业务逻辑统一抽取至 `@core/hooks/useToolsPage`，本文件仅保留 iOS 皮肤特有的 UI 渲染。
 */

import { m } from 'framer-motion'
import {
  Wrench, Database, CheckCircle2, XCircle, Save, ExternalLink, Clock,
} from 'lucide-react'
import {
  useToolsPage,
  formatWaybackTimestamp,
  snapshotViewUrl,
} from '@core/hooks/useToolsPage'
import { fadeInUp } from '@core/lib/animations'
import styles from './ToolsPage.module.scss'

export function ToolsPage() {
  const {
    t,
    tab, setTab,
    cdxUrl, setCdxUrl,
    cdxFrom, setCdxFrom,
    cdxTo, setCdxTo,
    cdxLimit, setCdxLimit,
    cdxLoading,
    cdxResults,
    handleCdxQuery,
    checkUrl, setCheckUrl,
    checkLoading,
    checkResult,
    handleCheck,
    canSave,
    saveUrl, setSaveUrl,
    saveLoading,
    saveResult,
    handleSave,
  } = useToolsPage()

  return (
    <div className={styles.page}>
      <m.div className={styles.hero} {...fadeInUp}>
        <h1 className={styles.heroTitle}>
          <Wrench size={28} className={styles.heroIcon} />
          {t('tools.title')}
        </h1>
        <p className={styles.heroSubtitle}>{t('tools.subtitle')}</p>
      </m.div>

      <div className={styles.segmented} role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'cdx'}
          className={`${styles.segment} ${tab === 'cdx' ? styles.segmentActive : ''}`}
          onClick={() => setTab('cdx')}
        >
          <Database size={14} />
          <span>{t('tools.cdx')}</span>
        </button>
        <button
          role="tab"
          aria-selected={tab === 'check'}
          className={`${styles.segment} ${tab === 'check' ? styles.segmentActive : ''}`}
          onClick={() => setTab('check')}
        >
          <CheckCircle2 size={14} />
          <span>{t('tools.check')}</span>
        </button>
        {canSave && (
          <button
            role="tab"
            aria-selected={tab === 'save'}
            className={`${styles.segment} ${tab === 'save' ? styles.segmentActive : ''}`}
            onClick={() => setTab('save')}
          >
            <Save size={14} />
            <span>{t('tools.save')}</span>
          </button>
        )}
      </div>

      {tab === 'cdx' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleCdxQuery}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="cdx-url">{t('tools.url')}</label>
              <input
                id="cdx-url"
                type="text"
                className={styles.input}
                placeholder={t('tools.urlPlaceholder')}
                value={cdxUrl}
                onChange={(e) => setCdxUrl(e.target.value)}
              />
            </div>
            <div className={styles.row}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="cdx-from">{t('tools.dateFrom')}</label>
                <input
                  id="cdx-from"
                  type="date"
                  className={styles.input}
                  value={cdxFrom}
                  onChange={(e) => setCdxFrom(e.target.value)}
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="cdx-to">{t('tools.dateTo')}</label>
                <input
                  id="cdx-to"
                  type="date"
                  className={styles.input}
                  value={cdxTo}
                  onChange={(e) => setCdxTo(e.target.value)}
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="cdx-limit">{t('tools.limit')}</label>
                <input
                  id="cdx-limit"
                  type="number"
                  min={1}
                  max={500}
                  className={styles.input}
                  value={cdxLimit}
                  onChange={(e) => setCdxLimit(Math.max(1, Number(e.target.value) || 50))}
                />
              </div>
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={cdxLoading || !cdxUrl.trim()}
            >
              {cdxLoading ? t('tools.querying') : t('tools.query')}
            </button>
          </form>

          {cdxResults.length === 0 && !cdxLoading && (
            <div className={styles.empty}>{t('tools.noSnapshots')}</div>
          )}

          {cdxResults.length > 0 && (
            <ul className={styles.list}>
              {cdxResults.map((s, i) => (
                <li key={`${s.timestamp}-${i}`} className={styles.listItem}>
                  <div className={styles.listMain}>
                    <div className={styles.listTimestamp}>{formatWaybackTimestamp(s.timestamp)}</div>
                    <div className={styles.listMeta}>
                      <span
                        className={
                          s.status_code >= 200 && s.status_code < 400
                            ? styles.statusOk
                            : styles.statusErr
                        }
                      >
                        {s.status_code}
                      </span>
                      <span className={styles.cellMuted}>{s.mime_type || '—'}</span>
                    </div>
                  </div>
                  <a
                    className={styles.link}
                    href={snapshotViewUrl(s.url, s.timestamp)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t('tools.snapshotUrl')} <ExternalLink size={14} />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === 'check' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleCheck}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="chk-url">{t('tools.url')}</label>
              <input
                id="chk-url"
                type="text"
                className={styles.input}
                placeholder={t('tools.urlPlaceholder')}
                value={checkUrl}
                onChange={(e) => setCheckUrl(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={checkLoading || !checkUrl.trim()}
            >
              {checkLoading ? t('tools.querying') : t('tools.query')}
            </button>
          </form>

          {checkResult && (
            <div
              className={`${styles.resultCard} ${
                checkResult.available ? styles.resultOk : styles.resultErr
              }`}
            >
              <div className={styles.resultHeader}>
                {checkResult.available ? (
                  <CheckCircle2 size={22} className={styles.iconOk} />
                ) : (
                  <XCircle size={22} className={styles.iconErr} />
                )}
                <span className={styles.resultTitle}>
                  {checkResult.available ? t('tools.available') : t('tools.notAvailable')}
                </span>
              </div>
              <div className={styles.resultBody}>
                <div className={styles.resultRow}>
                  <span className={styles.resultLabel}>URL</span>
                  <span className={styles.resultVal}>{checkResult.url}</span>
                </div>
                {checkResult.timestamp && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>
                      <Clock size={12} /> {t('tools.timestamp')}
                    </span>
                    <span className={styles.resultVal}>
                      {formatWaybackTimestamp(checkResult.timestamp)}
                    </span>
                  </div>
                )}
                {checkResult.status !== null && checkResult.status !== undefined && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>{t('tools.statusCode')}</span>
                    <span className={styles.resultVal}>{checkResult.status}</span>
                  </div>
                )}
                {checkResult.snapshot_url && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>{t('tools.snapshotUrl')}</span>
                    <a
                      className={styles.link}
                      href={checkResult.snapshot_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {checkResult.snapshot_url} <ExternalLink size={14} />
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {canSave && tab === 'save' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleSave}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="save-url">{t('tools.url')}</label>
              <input
                id="save-url"
                type="text"
                className={styles.input}
                placeholder={t('tools.urlPlaceholder')}
                value={saveUrl}
                onChange={(e) => setSaveUrl(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={saveLoading || !saveUrl.trim()}
            >
              {saveLoading ? t('tools.saving') : t('tools.saveSubmit')}
            </button>
          </form>

          {saveResult && (
            <div
              className={`${styles.resultCard} ${
                saveResult.success ? styles.resultOk : styles.resultErr
              }`}
            >
              <div className={styles.resultHeader}>
                {saveResult.success ? (
                  <CheckCircle2 size={22} className={styles.iconOk} />
                ) : (
                  <XCircle size={22} className={styles.iconErr} />
                )}
                <span className={styles.resultTitle}>
                  {saveResult.success ? t('tools.saveSuccess') : t('tools.saveFailed')}
                </span>
              </div>
              <div className={styles.resultBody}>
                <div className={styles.resultRow}>
                  <span className={styles.resultLabel}>URL</span>
                  <span className={styles.resultVal}>{saveResult.url}</span>
                </div>
                {saveResult.timestamp && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>
                      <Clock size={12} /> {t('tools.timestamp')}
                    </span>
                    <span className={styles.resultVal}>
                      {formatWaybackTimestamp(saveResult.timestamp)}
                    </span>
                  </div>
                )}
                {saveResult.snapshot_url && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>{t('tools.snapshotUrl')}</span>
                    <a
                      className={styles.link}
                      href={saveResult.snapshot_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {saveResult.snapshot_url} <ExternalLink size={14} />
                    </a>
                  </div>
                )}
                {saveResult.error && (
                  <div className={styles.resultRow}>
                    <span className={styles.resultLabel}>Error</span>
                    <span className={styles.resultVal}>{saveResult.error}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
