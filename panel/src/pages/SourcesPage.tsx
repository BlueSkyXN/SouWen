import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { RefreshCw, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Badge } from '../components/common/Badge'
import { Spinner } from '../components/common/Spinner'
import { formatError } from '../lib/errors'
import type { DoctorResponse, DoctorSource } from '../types'
import styles from './SourcesPage.module.scss'

const staggerContainer = {
  animate: { transition: { staggerChildren: 0.03 } },
}
const staggerItem = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
}

export function SourcesPage() {
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
      addToast('error', t('sources.fetchFailed', { message: formatError(err) }))
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
        <div className={styles.summary}>
          <Badge color="red">{t('common.error')}</Badge>
          <button className="btn btn-sm btn-outline" onClick={fetchData}>
            <RefreshCw size={14} /> {t('sources.refresh')}
          </button>
        </div>
      </div>
    )
  }

  const okCount = doctor.ok
  const totalCount = doctor.total

  const tiers = [0, 1, 2]
  const sourcesByTier: Record<number, DoctorSource[]> = {}
  for (const tier of tiers) {
    sourcesByTier[tier] = doctor.sources.filter((s) => s.tier === tier)
  }

  const tierLabelKeys: Record<number, string> = {
    0: 'sources.tier0',
    1: 'sources.tier1',
    2: 'sources.tier2',
  }

  const tierColors: Record<number, 'green' | 'blue' | 'amber'> = {
    0: 'green',
    1: 'blue',
    2: 'amber',
  }

  return (
    <div className={styles.page}>
      <div className={styles.summary}>
        <Badge color={okCount === totalCount ? 'green' : 'amber'}>
          {t('sources.sourcesAvailable', { ok: okCount, total: totalCount })}
        </Badge>
        <button className="btn btn-sm btn-outline" onClick={fetchData}>
          <RefreshCw size={14} /> {t('sources.refresh')}
        </button>
      </div>

      {tiers.map((tier) => {
        const list = sourcesByTier[tier]
        if (!list || list.length === 0) return null
        return (
          <div key={tier} className={styles.tierGroup}>
            <h3 className={styles.tierTitle}>
              <Badge color={tierColors[tier]}>{t(tierLabelKeys[tier])}</Badge>
              <span className={styles.tierCount}>({list.length})</span>
            </h3>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t('sources.status')}</th>
                    <th>{t('sources.name')}</th>
                    <th>{t('sources.type')}</th>
                    <th>{t('sources.requiredKey')}</th>
                    <th>{t('sources.description')}</th>
                  </tr>
                </thead>
                <m.tbody variants={staggerContainer} initial="initial" animate="animate">
                  {list.map((src) => (
                    <m.tr key={src.name} variants={staggerItem}>
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
                          {t(`dashboard.${src.category}`)}
                        </Badge>
                      </td>
                      <td>
                        <code className={styles.code}>{src.required_key ?? '—'}</code>
                      </td>
                      <td className={styles.message}>{src.message}</td>
                    </m.tr>
                  ))}
                </m.tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}
