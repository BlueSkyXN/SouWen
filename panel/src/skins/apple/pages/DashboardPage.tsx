import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse } from '@core/types'
import styles from './DashboardPage.module.scss'

export function DashboardPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
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
  const okCount = doctor.ok
  const totalCount = doctor.total
  const healthPct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  return (
    <div className={styles.page}>
      {/* ── Hero Section ── */}
      <div className={styles.heroSection}>
        <div className={styles.heroSubtitle}>SouWen {t('dashboard.title', 'Dashboard')}</div>
        <h1 className={styles.heroTitle}>
          {healthPct > 50
            ? t('dashboard.heroHealthy', '掌控全局，就是这么简单。')
            : t('dashboard.heroDegraded', '部分服务降级，请检查配置。')}
        </h1>
        <p className={styles.heroDesc}>
          {t('dashboard.heroDesc', '核心指标一目了然。无论是论文数据库的实时状态，还是专利接口的探测情况，尽在掌握。')}
        </p>

        {/* ── Giant Metric Numbers ── */}
        <div className={styles.metricsRow}>
          <div className={styles.metricItem}>
            <div className={styles.metricLabel}>{t('dashboard.paperSources')}</div>
            <div className={styles.metricValue}>{paperCount}</div>
            <div className={styles.metricDesc}>{t('dashboard.ready', '就绪')}</div>
          </div>
          <div className={styles.metricItem}>
            <div className={styles.metricLabel}>{t('dashboard.patentSources')}</div>
            <div className={styles.metricValue}>{patentCount}</div>
            <div className={styles.metricDesc}>{t('dashboard.ready', '就绪')}</div>
          </div>
          <div className={styles.metricItem}>
            <div className={styles.metricLabel}>{t('dashboard.availableSources')}</div>
            <div className={styles.metricValue}>
              {okCount}<span className={styles.metricFraction}>/{totalCount}</span>
            </div>
            <div className={`${styles.metricDesc} ${healthPct <= 50 ? styles.metricDescAlert : ''}`}>
              {healthPct > 50
                ? t('dashboard.statusOk', 'Healthy')
                : t('dashboard.statusDegraded', 'Degraded')}
            </div>
          </div>
        </div>
      </div>

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
