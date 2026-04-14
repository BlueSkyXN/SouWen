import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { RefreshCw, CheckCircle2, XCircle, Ban, ToggleLeft, ToggleRight } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Badge } from '../components/common/Badge'
import { TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '../lib/errors'
import { staggerContainerFast, staggerItemSmall } from '../lib/animations'
import { categoryBadgeColor, categoryLabel } from '../lib/ui'
import type { DoctorResponse, DoctorSource } from '../types'
import styles from './SourcesPage.module.scss'

function StatusIcon({ status }: { status: string }) {
  if (status === 'ok') return <CheckCircle2 size={18} style={{ color: 'var(--success)' }} />
  if (status === 'disabled') return <Ban size={18} style={{ color: 'var(--muted)' }} />
  return <XCircle size={18} style={{ color: 'var(--error)' }} />
}

export function SourcesPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
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

  const handleToggle = useCallback(async (name: string, currentEnabled: boolean) => {
    setToggling(name)
    try {
      await api.updateSourceConfig(name, { enabled: !currentEnabled })
      await fetchData()
      addToast('success', `${name} ${!currentEnabled ? '已启用' : '已禁用'}`)
    } catch (err) {
      addToast('error', formatError(err))
    } finally {
      setToggling(null)
    }
  }, [fetchData, addToast])

  if (loading) return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <span className="srOnly">{t('common.loading', 'Loading sources')}</span>
      <TableSkeleton rows={8} cols={5} />
    </div>
  )

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
                    <th style={{ width: '4rem', textAlign: 'center' }}>启用</th>
                  </tr>
                </thead>
                <m.tbody variants={staggerContainerFast} initial="initial" animate="animate">
                  {list.map((src) => (
                    <m.tr key={src.name} variants={staggerItemSmall} style={{ opacity: src.enabled ? 1 : 0.5 }}>
                      <td><StatusIcon status={src.status} /></td>
                      <td className={styles.sourceName}>{src.name}</td>
                      <td>
                        <Badge color={categoryBadgeColor(src.category)}>
                          {categoryLabel(t, src.category)}
                        </Badge>
                      </td>
                      <td>
                        <code className={styles.code}>{src.required_key ?? '—'}</code>
                      </td>
                      <td className={styles.message}>
                        {src.message}
                        {src.channel && Object.keys(src.channel).length > 0 && (
                          <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', opacity: 0.7 }}>
                            [{Object.entries(src.channel).map(([k, v]) => `${k}=${v}`).join(', ')}]
                          </span>
                        )}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <button
                          className="btn btn-sm btn-ghost"
                          onClick={() => handleToggle(src.name, src.enabled)}
                          disabled={toggling === src.name}
                          title={src.enabled ? '点击禁用' : '点击启用'}
                          style={{ padding: '0.25rem' }}
                        >
                          {src.enabled
                            ? <ToggleRight size={20} style={{ color: 'var(--success)' }} />
                            : <ToggleLeft size={20} style={{ color: 'var(--muted)' }} />}
                        </button>
                      </td>
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
