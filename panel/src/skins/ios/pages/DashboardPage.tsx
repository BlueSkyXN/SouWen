/**
 * 文件用途：iOS 皮肤的仪表板页面，展示系统健康状态、数据源统计和健康检查结果
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Activity, FileText, Shield, Globe, RefreshCw } from 'lucide-react'
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
      <h1 className={styles.pageTitle}>{t('dashboard.title', '仪表盘')}</h1>

      {/* ── Stat Cards ── */}
      <m.div
        className={styles.statsGrid}
        variants={staggerContainer}
        initial="initial"
        animate="animate"
      >
        <m.div variants={staggerItem} className={styles.statCard}>
          <span className={styles.statIcon} style={{ background: '#007aff' }}>
            <FileText size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{paperCount}</div>
            <div className={styles.statLabel}>{t('dashboard.paperSources')}</div>
          </div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <span className={styles.statIcon} style={{ background: '#ff9500' }}>
            <Shield size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{patentCount}</div>
            <div className={styles.statLabel}>{t('dashboard.patentSources')}</div>
          </div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <span className={styles.statIcon} style={{ background: '#34c759' }}>
            <Globe size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{webCount}</div>
            <div className={styles.statLabel}>{t('dashboard.webEngines')}</div>
          </div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <span className={styles.statIcon} style={{ background: '#5856d6' }}>
            <Activity size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>
              {okCount}<span className={styles.statFraction}>/{totalCount}</span>
            </div>
            <div className={styles.statLabel}>{t('dashboard.availableSources')}</div>
          </div>
        </m.div>
      </m.div>

      {/* ── Health Status ── */}
      <div className={styles.formGroup}>
        <div className={styles.groupTitle}>{t('dashboard.sourceHealth')}</div>
        <div className={styles.groupCard}>
          {/* Summary row */}
          <div className={styles.formRow}>
            <span className={styles.rowLabel}>{t('dashboard.health', 'Health')}</span>
            <span className={styles.rowValue}>
              <span className={`${styles.statusDot} ${healthPct > 50 ? styles.statusOk : styles.statusErr}`} />
              {healthPct}% — {healthPct > 50 ? t('dashboard.statusOk', 'Healthy') : t('dashboard.statusDegraded', 'Degraded')}
            </span>
          </div>
          {version && (
            <div className={styles.formRow}>
              <span className={styles.rowLabel}>{t('dashboard.version', 'Version')}</span>
              <span className={styles.rowValueMuted}>v{version}</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Source List ── */}
      <div className={styles.formGroup}>
        <div className={styles.groupTitle}>{t('dashboard.name', 'Sources')}</div>
        <div className={styles.groupCard}>
          {doctor.sources.map((src, i) => {
            const statusClass = src.status === 'ok'
              ? styles.statusOk
              : src.status === 'needs_key'
                ? styles.statusWarn
                : styles.statusErr

            return (
              <div key={src.name} className={`${styles.formRow} ${i < doctor.sources.length - 1 ? styles.formRowSep : ''}`}>
                <div className={styles.sourceInfo}>
                  <span className={`${styles.statusDot} ${statusClass}`} />
                  <span className={styles.sourceName}>{src.name}</span>
                  <span className={styles.typeBadge}>{src.category}</span>
                </div>
                <span className={styles.rowValueMuted}>T{src.tier}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
