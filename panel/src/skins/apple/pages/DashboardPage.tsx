import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Activity, RefreshCw } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { useAuthStore } from '@core/stores/authStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse } from '@core/types'
import styles from './DashboardPage.module.scss'

export function DashboardPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const version = useAuthStore((s) => s.version)
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setFetchError(false)
    try {
      const d = await api.getDoctor()
      setDoctor(d)
    } catch (err) {
      setFetchError(true)
      addToast('error', t('dashboard.fetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  if (loading) {
    return <Spinner label={t('common.loading', 'Loading...')} />
  }

  if (fetchError || !doctor) {
    return (
      <div className={styles.errorState}>
        <p>{t('dashboard.fetchFailed', { message: '' })}</p>
        <button className={styles.retryBtn} onClick={fetchData}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          {t('sources.refresh')}
        </button>
      </div>
    )
  }

  const paperCount = doctor.sources.filter((s) => s.category === 'paper').length
  const patentCount = doctor.sources.filter((s) => s.category === 'patent').length
  const webCount = doctor.sources.filter((s) => s.category === 'web').length
  const okCount = doctor.ok
  const totalCount = doctor.total
  const healthPct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  return (
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <Activity size={20} />
          {t('dashboard.title', 'Dashboard')}
        </h1>
        <div className={styles.headerBadges}>
          <span className={styles.uptimeBadge}>
            {t('dashboard.health', 'Health')}: {healthPct}%
          </span>
          {version && (
            <span className={styles.uptimeBadge}>v{version}</span>
          )}
          <span className={`${styles.statusBadge} ${healthPct > 50 ? styles.ok : styles.err}`}>
            {healthPct > 50 ? t('dashboard.statusOk', 'Healthy') : t('dashboard.statusDegraded', 'Degraded')}
          </span>
        </div>
      </div>

      {/* ── Stats Grid ── */}
      <m.div
        className={styles.statsGrid}
        variants={staggerContainer}
        initial="initial"
        animate="animate"
      >
        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statLabel}>{t('dashboard.paperSources')}</div>
          <div className={styles.statValue}>{paperCount}</div>
          <div className={styles.statDesc}>{t('dashboard.paperSources')}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statLabel}>{t('dashboard.patentSources')}</div>
          <div className={styles.statValue}>{patentCount}</div>
          <div className={styles.statDesc}>{t('dashboard.patentSources')}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statLabel}>{t('dashboard.webEngines')}</div>
          <div className={styles.statValue}>{webCount}</div>
          <div className={styles.statDesc}>{t('dashboard.webEngines')}</div>
        </m.div>

        <m.div variants={staggerItem} className={`${styles.statCard} ${styles.statCardHighlight}`}>
          <div className={styles.statLabel}>{t('dashboard.availableSources')}</div>
          <div className={styles.statValue}>
            {okCount}<span className={styles.statFraction}>/{totalCount}</span>
          </div>
          <div className={styles.statDesc}>{t('dashboard.availableSources')}</div>
        </m.div>
      </m.div>

      {/* ── Health Table ── */}
      <div className={styles.tableSection}>
        <h3 className={styles.sectionTitle}>{t('dashboard.sourceHealth')}</h3>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t('dashboard.status')}</th>
                <th>{t('dashboard.name', 'Name')}</th>
                <th>{t('dashboard.type')}</th>
                <th>{t('dashboard.tier')}</th>
                <th>{t('dashboard.requiredKey')}</th>
                <th>{t('dashboard.diagnostics', 'Details')}</th>
              </tr>
            </thead>
            <tbody>
              {doctor.sources.map((src) => {
                const statusClass = src.status === 'ok'
                  ? styles.statusOk
                  : src.status === 'needs_key'
                    ? styles.statusWarn
                    : styles.statusErr
                const statusLabel = src.status === 'ok'
                  ? t('dashboard.ok', 'OK')
                  : src.status === 'needs_key'
                    ? t('dashboard.needsKey', 'Needs Key')
                    : t('dashboard.error', 'Error')

                return (
                  <tr key={src.name}>
                    <td>
                      <span className={`${styles.statusIndicator} ${statusClass}`}>
                        <span className={styles.statusDot} />
                        {statusLabel}
                      </span>
                    </td>
                    <td className={styles.nodeName}>{src.name}</td>
                    <td>
                      <span className={`${styles.typeBadge} ${styles[src.category]}`}>
                        {src.category}
                      </span>
                    </td>
                    <td>
                      <span className={styles.tierBadge}>T{src.tier}</span>
                    </td>
                    <td>
                      <code className={styles.keyCode}>{src.required_key ?? '—'}</code>
                    </td>
                    <td className={styles.diagMessage}>{src.message}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
