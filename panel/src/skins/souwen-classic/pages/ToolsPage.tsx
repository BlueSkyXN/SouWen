/**
 * 工具箱页面 - Classic 皮肤版本
 *
 * 文件用途：Wayback Machine 网页归档查询与存档工具集合
 *
 * 三个 Tab：
 *   - cdx: CDX 快照查询（按 URL + 日期范围列出所有快照）
 *   - check: 可用性检测（查询某 URL 是否有快照）
 *   - save: 提交存档请求（保存当前 URL 到 Wayback Machine）
 */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Wrench, Database, CheckCircle2, XCircle, Save, ExternalLink, Clock,
} from 'lucide-react'
import { api } from '@core/services/api'
import type {
  WaybackSnapshot,
  WaybackAvailabilityResponse,
  WaybackSaveResponse,
} from '@core/types'
import { useNotificationStore } from '@core/stores/notificationStore'
import { fadeInUp } from '@core/lib/animations'
import styles from './ToolsPage.module.scss'

type Tab = 'cdx' | 'check' | 'save'

function formatWaybackTimestamp(ts: string): string {
  // Wayback timestamp format: YYYYMMDDhhmmss
  if (!ts || ts.length < 8) return ts
  const yyyy = ts.slice(0, 4)
  const mm = ts.slice(4, 6)
  const dd = ts.slice(6, 8)
  const hh = ts.length >= 10 ? ts.slice(8, 10) : '00'
  const mi = ts.length >= 12 ? ts.slice(10, 12) : '00'
  const ss = ts.length >= 14 ? ts.slice(12, 14) : '00'
  try {
    const d = new Date(`${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}Z`)
    if (isNaN(d.getTime())) return ts
    return d.toLocaleString()
  } catch {
    return ts
  }
}

function snapshotViewUrl(url: string, timestamp: string): string {
  return `https://web.archive.org/web/${timestamp}/${url}`
}

export function ToolsPage() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [tab, setTab] = useState<Tab>('cdx')
  const abortRef = useRef<AbortController | null>(null)

  // CDX state
  const [cdxUrl, setCdxUrl] = useState('')
  const [cdxFrom, setCdxFrom] = useState('')
  const [cdxTo, setCdxTo] = useState('')
  const [cdxLimit, setCdxLimit] = useState(50)
  const [cdxLoading, setCdxLoading] = useState(false)
  const [cdxResults, setCdxResults] = useState<WaybackSnapshot[]>([])

  // Check state
  const [checkUrl, setCheckUrl] = useState('')
  const [checkLoading, setCheckLoading] = useState(false)
  const [checkResult, setCheckResult] = useState<WaybackAvailabilityResponse | null>(null)

  // Save state
  const [saveUrl, setSaveUrl] = useState('')
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveResult, setSaveResult] = useState<WaybackSaveResponse | null>(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const cancelInflight = () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    return abortRef.current.signal
  }

  // Convert YYYY-MM-DD → YYYYMMDD for wayback CDX API
  const toWaybackDate = (s: string): string | undefined => {
    const trimmed = s.trim()
    if (!trimmed) return undefined
    return trimmed.replace(/-/g, '')
  }

  const handleCdxQuery = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!cdxUrl.trim()) return
    const signal = cancelInflight()
    setCdxLoading(true)
    setCdxResults([])
    try {
      const res = await api.waybackCDX(
        cdxUrl.trim(),
        {
          from: toWaybackDate(cdxFrom),
          to: toWaybackDate(cdxTo),
          limit: cdxLimit,
        },
        signal,
      )
      setCdxResults(res.snapshots ?? [])
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setCdxLoading(false)
    }
  }

  const handleCheck = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!checkUrl.trim()) return
    const signal = cancelInflight()
    setCheckLoading(true)
    setCheckResult(null)
    try {
      const res = await api.waybackCheck(checkUrl.trim(), undefined, signal)
      setCheckResult(res)
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setCheckLoading(false)
    }
  }

  const handleSave = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!saveUrl.trim()) return
    const signal = cancelInflight()
    setSaveLoading(true)
    setSaveResult(null)
    try {
      const res = await api.waybackSave(saveUrl.trim(), 60, signal)
      setSaveResult(res)
      if (res.success) {
        addToast('success', t('tools.saveSuccess'))
      } else {
        addToast('error', res.error || t('tools.saveFailed'))
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setSaveLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <m.div className={styles.hero} {...fadeInUp}>
        <h1 className={styles.heroTitle}>
          <Wrench size={28} className={styles.heroIcon} />
          {t('tools.title')}
        </h1>
        <p className={styles.heroSubtitle}>{t('tools.subtitle')}</p>
      </m.div>

      <div className={styles.tabs} role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'cdx'}
          className={`${styles.tab} ${tab === 'cdx' ? styles.tabActive : ''}`}
          onClick={() => setTab('cdx')}
        >
          <Database size={14} /> {t('tools.cdx')}
        </button>
        <button
          role="tab"
          aria-selected={tab === 'check'}
          className={`${styles.tab} ${tab === 'check' ? styles.tabActive : ''}`}
          onClick={() => setTab('check')}
        >
          <CheckCircle2 size={14} /> {t('tools.check')}
        </button>
        <button
          role="tab"
          aria-selected={tab === 'save'}
          className={`${styles.tab} ${tab === 'save' ? styles.tabActive : ''}`}
          onClick={() => setTab('save')}
        >
          <Save size={14} /> {t('tools.save')}
        </button>
      </div>

      {tab === 'cdx' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleCdxQuery}>
            <div className={`${styles.field} ${styles.fieldFull}`}>
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
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={cdxLoading || !cdxUrl.trim()}
            >
              {cdxLoading ? t('tools.querying') : t('tools.query')}
            </button>
          </form>

          {cdxResults.length === 0 && !cdxLoading && (
            <div className={styles.empty}>{t('tools.noSnapshots')}</div>
          )}

          {cdxResults.length > 0 && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t('tools.timestamp')}</th>
                    <th>{t('tools.statusCode')}</th>
                    <th>MIME</th>
                    <th>{t('tools.snapshotUrl')}</th>
                  </tr>
                </thead>
                <tbody>
                  {cdxResults.map((s, i) => (
                    <tr key={`${s.timestamp}-${i}`}>
                      <td className={styles.cellMono}>
                        {formatWaybackTimestamp(s.timestamp)}
                      </td>
                      <td>
                        <span
                          className={
                            s.status_code >= 200 && s.status_code < 400
                              ? styles.statusOk
                              : styles.statusErr
                          }
                        >
                          {s.status_code}
                        </span>
                      </td>
                      <td className={styles.cellMuted}>{s.mime_type || '—'}</td>
                      <td>
                        <a
                          className={styles.link}
                          href={snapshotViewUrl(s.url, s.timestamp)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {t('tools.snapshotUrl')} <ExternalLink size={12} />
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === 'check' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleCheck}>
            <div className={`${styles.field} ${styles.fieldFull}`}>
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
              className={styles.primaryBtn}
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
                  <CheckCircle2 size={20} className={styles.iconOk} />
                ) : (
                  <XCircle size={20} className={styles.iconErr} />
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
                      {checkResult.snapshot_url} <ExternalLink size={12} />
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'save' && (
        <section className={styles.panel}>
          <form className={styles.form} onSubmit={handleSave}>
            <div className={`${styles.field} ${styles.fieldFull}`}>
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
              className={styles.primaryBtn}
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
                  <CheckCircle2 size={20} className={styles.iconOk} />
                ) : (
                  <XCircle size={20} className={styles.iconErr} />
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
                      {saveResult.snapshot_url} <ExternalLink size={12} />
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
