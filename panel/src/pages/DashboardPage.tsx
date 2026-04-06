import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { CheckCircle2, XCircle, FileText, Shield, Globe } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { useAuthStore } from '../stores/authStore'
import { Card } from '../components/common/Card'
import { Badge } from '../components/common/Badge'
import { Spinner } from '../components/common/Spinner'
import { formatError } from '../lib/errors'
import type { DoctorResponse } from '../types'
import styles from './DashboardPage.module.scss'

const staggerContainer = {
  animate: { transition: { staggerChildren: 0.05 } },
}
const staggerItem = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
}

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

  if (loading) return <Spinner size="lg" label={t('common.loading')} />

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
        <m.div variants={staggerItem}>
          <Card title={t('dashboard.paperSources')}>
            <div className={styles.cardIcon}><FileText size={20} /></div>
            <div className={styles.cardValue}>{paperCount}</div>
          </Card>
        </m.div>
        <m.div variants={staggerItem}>
          <Card title={t('dashboard.patentSources')}>
            <div className={styles.cardIcon}><Shield size={20} /></div>
            <div className={styles.cardValue}>{patentCount}</div>
          </Card>
        </m.div>
        <m.div variants={staggerItem}>
          <Card title={t('dashboard.webEngines')}>
            <div className={styles.cardIcon}><Globe size={20} /></div>
            <div className={styles.cardValue}>{webCount}</div>
          </Card>
        </m.div>
        <m.div variants={staggerItem}>
          <Card title={t('dashboard.availableSources')}>
            <div className={styles.cardValue}>
              {okCount} / {totalCount}
            </div>
          </Card>
        </m.div>
        <m.div variants={staggerItem}>
          <Card title={t('dashboard.healthRate')}>
            <div
              className={styles.cardValue}
              style={{ color: healthPct >= 80 ? 'var(--success)' : healthPct >= 50 ? 'var(--warning)' : 'var(--error)' }}
            >
              {healthPct}%
            </div>
          </Card>
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
                  <Badge
                    color={
                      src.category === 'paper'
                        ? 'blue'
                        : src.category === 'patent'
                          ? 'amber'
                          : 'green'
                    }
                  >
                    {src.category === 'paper'
                      ? t('dashboard.paper')
                      : src.category === 'patent'
                        ? t('dashboard.patent')
                        : t('dashboard.web')}
                  </Badge>
                </td>
                <td>
                  <Badge
                    color={
                      src.tier === 0
                        ? 'green'
                        : src.tier === 1
                          ? 'blue'
                          : 'amber'
                    }
                  >
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
