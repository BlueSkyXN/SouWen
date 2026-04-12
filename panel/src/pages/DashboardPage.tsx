import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { CheckCircle2, XCircle, FileText, Shield, Globe, Layers } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { useAuthStore } from '../stores/authStore'
import { Card } from '../components/common/Card'
import { Badge } from '../components/common/Badge'
import { StatsGridSkeleton, TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '../lib/errors'
import { staggerContainer, staggerItem } from '../lib/animations'
import { categoryBadgeColor, tierBadgeColor, categoryLabel } from '../lib/ui'
import type { DoctorResponse } from '../types'
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

  if (loading) return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <span className="srOnly">{t('common.loading', 'Loading dashboard data')}</span>
      <Card style={{ marginBottom: 24 }}>
        <div className={styles.serverInfo}>
          <div style={{ width: '100%', height: 20, background: 'var(--bg-subtle)', borderRadius: 6 }} />
        </div>
      </Card>
      <StatsGridSkeleton count={5} />
      <TableSkeleton rows={6} cols={4} />
    </div>
  )

  if (fetchError || !doctor) {
    return (
      <div className={styles.page}>
        <Card style={{ marginBottom: 24 }}>
          <div className={styles.serverInfo}>
            <div>
              <span className={styles.serverLabel}>{t('dashboard.status')}</span>
              <Badge color="red">{t('common.error')}</Badge>
            </div>
            <div>
              <button className="btn btn-sm btn-outline" onClick={fetchData}>{t('sources.refresh')}</button>
            </div>
          </div>
        </Card>
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
      <Card style={{ marginBottom: 24 }}>
        <div className={styles.serverInfo}>
          <div>
            <span className={styles.serverLabel}>{t('dashboard.status')}</span>
            <Badge color="green">{t('dashboard.running')}</Badge>
          </div>
          <div>
            <span className={styles.serverLabel}>{t('dashboard.version')}</span>
            <span className={styles.serverValue}>{version || '—'}</span>
          </div>
          <div>
            <span className={styles.serverLabel}>{t('dashboard.availableSources')}</span>
            <span className={styles.serverValue}>
              {okCount} / {totalCount}
            </span>
          </div>
        </div>
      </Card>

      <m.div className={styles.statsGrid} variants={staggerContainer} initial="initial" animate="animate">
        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statTitle}>{t('dashboard.paperSources')}</span>
            <div className={`${styles.statIcon} ${styles.iconBlue}`}><FileText size={18} /></div>
          </div>
          <div className={styles.statValue}>{paperCount}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statTitle}>{t('dashboard.patentSources')}</span>
            <div className={`${styles.statIcon} ${styles.iconAmber}`}><Shield size={18} /></div>
          </div>
          <div className={styles.statValue}>{patentCount}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statTitle}>{t('dashboard.webEngines')}</span>
            <div className={`${styles.statIcon} ${styles.iconGreen}`}><Globe size={18} /></div>
          </div>
          <div className={styles.statValue}>{webCount}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statTitle}>{t('dashboard.availableSources')}</span>
            <div className={`${styles.statIcon} ${styles.iconIndigo}`}><Layers size={18} /></div>
          </div>
          <div className={styles.statValue}>{okCount} / {totalCount}</div>
        </m.div>

        <m.div variants={staggerItem} className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statTitle}>{t('dashboard.healthRate')}</span>
          </div>
          <div className={styles.healthRing}>
            <svg width="80" height="80" viewBox="0 0 80 80" role="img" aria-label={`${t('dashboard.healthRate')}: ${healthPct}%`}>
              <title>{t('dashboard.healthRate')}: {healthPct}%</title>
              <circle cx="40" cy="40" r="34" fill="none" stroke="var(--border)" strokeWidth="6" />
              <circle
                cx="40" cy="40" r="34" fill="none"
                stroke={healthPct >= 80 ? 'var(--success)' : healthPct >= 50 ? 'var(--warning)' : 'var(--error)'}
                strokeWidth="6"
                strokeDasharray={`${healthPct * 2.136} ${213.6 - healthPct * 2.136}`}
                strokeDashoffset="53.4"
                strokeLinecap="round"
                style={{ transition: 'stroke-dasharray 0.8s ease' }}
              />
              <text x="40" y="44" textAnchor="middle" fill="var(--text)" fontSize="18" fontWeight="700">
                {healthPct}%
              </text>
            </svg>
          </div>
        </m.div>
      </m.div>

      <h3 className={styles.sectionTitle}>{t('dashboard.sourceHealth')}</h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t('dashboard.status')}</th>
              <th>{t('dashboard.source')}</th>
              <th>{t('dashboard.type')}</th>
              <th>{t('dashboard.tier')}</th>
              <th>{t('dashboard.requiredKey')}</th>
              <th>{t('dashboard.description')}</th>
            </tr>
          </thead>
          <tbody>
            {doctor?.sources.map((src) => (
              <tr key={src.name}>
                <td>
                  {src.status === 'ok' ? (
                    <CheckCircle2 size={18} style={{ color: 'var(--success)' }} />
                  ) : (
                    <XCircle size={18} style={{ color: 'var(--error)' }} />
                  )}
                </td>
                <td className={styles.sourceName}>{src.name}</td>
                <td>
                  <Badge color={categoryBadgeColor(src.category)}>
                    {categoryLabel(t, src.category)}
                  </Badge>
                </td>
                <td>
                  <Badge color={tierBadgeColor(src.tier)}>
                    Tier {src.tier}
                  </Badge>
                </td>
                <td>
                  <code className={styles.code}>{src.required_key ?? '—'}</code>
                </td>
                <td className={styles.message}>{src.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
