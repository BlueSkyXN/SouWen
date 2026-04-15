import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { RefreshCw, FileText, Shield, Globe, Key, Star, Check, Sparkles, Zap } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Modal } from '../components/common/Modal'
import { EmptyState } from '../components/common/EmptyState'
import { Skeleton } from '../components/common/Skeleton'
import { formatError } from '../lib/errors'
import { staggerContainerFast, staggerItemSmall } from '../lib/animations'

import type { DoctorResponse, DoctorSource } from '../types'
import styles from './SourcesPage.module.scss'

type CategoryKey = 'paper' | 'patent' | 'web'

const CATEGORY_ORDER: CategoryKey[] = ['paper', 'patent', 'web']

const CATEGORY_ICONS: Record<CategoryKey, typeof FileText> = {
  paper: FileText,
  patent: Shield,
  web: Globe,
}

const CATEGORY_STYLE: Record<CategoryKey, string> = {
  paper: styles.categoryPaper,
  patent: styles.categoryPatent,
  web: styles.categoryWeb,
}

function statusBorderClass(src: DoctorSource): string {
  if (!src.enabled) return styles.borderDisabled
  switch (src.status) {
    case 'ok': return styles.borderOk
    case 'needs_key': return styles.borderWarning
    default: return styles.borderError
  }
}

function StatusDot({ status }: { status: string }) {
  const cls =
    status === 'ok'
      ? styles.statusOk
      : status === 'disabled'
        ? styles.statusDisabled
        : status === 'needs_key'
          ? styles.statusWarning
          : styles.statusError
  return <span className={`${styles.statusDot} ${cls}`} />
}

function TierBadge({ tier, t }: { tier: number; t: (k: string) => string }) {
  if (tier === 0) {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge0}`}>
        <Star size={10} /> {t('sources.tierCore')}
      </span>
    )
  }
  if (tier === 1) {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge1}`}>
        <Zap size={10} /> {t('sources.tierExtended')}
      </span>
    )
  }
  return (
    <span className={`${styles.tierBadge} ${styles.tierBadge2}`}>
      <Sparkles size={10} /> {t('sources.tierExperimental')}
    </span>
  )
}

function SourceCardSkeleton() {
  return (
    <div className={styles.skeletonCard}>
      <Skeleton variant="textShort" width="50%" />
      <Skeleton variant="text" width="30%" />
      <Skeleton variant="textLong" width="90%" />
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <div className={styles.skeletonPageHeader}>
        <Skeleton variant="textShort" width={200} />
        <Skeleton variant="text" width={280} />
      </div>
      {[0, 1, 2].map((g) => (
        <div key={g}>
          <div className={styles.skeletonHeader}>
            <Skeleton variant="rect" width={44} height={44} />
            <Skeleton variant="textShort" width={120} />
          </div>
          <div className={styles.skeletonGrid}>
            {Array.from({ length: 3 }, (_, i) => (
              <SourceCardSkeleton key={i} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function SourcesPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [confirmSource, setConfirmSource] = useState<DoctorSource | null>(null)
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

  const executeToggle = useCallback(async (name: string, currentEnabled: boolean) => {
    setToggling(name)
    try {
      await api.updateSourceConfig(name, { enabled: !currentEnabled })
      await fetchData()
      addToast(
        'success',
        `${name} ${!currentEnabled ? t('sources.enabled') : t('sources.disabled')}`,
      )
    } catch (err) {
      addToast('error', formatError(err))
    } finally {
      setToggling(null)
    }
  }, [fetchData, addToast, t])

  const handleToggle = useCallback((src: DoctorSource) => {
    if (src.enabled && src.status === 'ok') {
      setConfirmSource(src)
    } else {
      void executeToggle(src.name, src.enabled)
    }
  }, [executeToggle])

  const handleConfirmDisable = useCallback(() => {
    if (!confirmSource) return
    void executeToggle(confirmSource.name, confirmSource.enabled)
    setConfirmSource(null)
  }, [confirmSource, executeToggle])

  if (loading) return <LoadingSkeleton />

  if (fetchError || !doctor) {
    return (
      <div className={styles.page}>
        <EmptyState
          type="error"
          title={t('sources.errorTitle')}
          description={t('sources.errorDescription')}
          action={
            <button className="btn btn-sm btn-outline" onClick={fetchData}>
              <RefreshCw size={14} /> {t('common.retry')}
            </button>
          }
        />
      </div>
    )
  }

  const okCount = doctor.ok
  const totalCount = doctor.total

  const sourcesByCategory: Record<string, DoctorSource[]> = {}
  for (const cat of CATEGORY_ORDER) {
    sourcesByCategory[cat] = doctor.sources.filter((s) => s.category === cat)
  }

  const categoryI18nKeys: Record<string, string> = {
    paper: 'sources.categoryPaper',
    patent: 'sources.categoryPatent',
    web: 'sources.categoryWeb',
  }

  const healthPercent = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  return (
    <div className={styles.page}>
      {/* Page Header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h1 className={styles.pageTitle}>{t('sources.pageTitle')}</h1>
          <p className={styles.pageSubtitle}>{t('sources.pageSubtitle')}</p>
        </div>
        <div className={styles.pageHeaderRight}>
          <div className={styles.healthStats}>
            <span className={styles.healthLabel}>
              {t('sources.healthStats', { ok: okCount, total: totalCount })}
            </span>
            <div className={styles.healthBar}>
              <div
                className={styles.healthBarFill}
                style={{ width: `${healthPercent}%` }}
                data-full={okCount === totalCount ? '' : undefined}
              />
            </div>
          </div>
          <button className="btn btn-sm btn-outline" onClick={fetchData}>
            <RefreshCw size={14} /> {t('sources.refresh')}
          </button>
        </div>
      </div>

      {/* Category Groups */}
      {CATEGORY_ORDER.map((cat) => {
        const list = sourcesByCategory[cat]
        if (!list || list.length === 0) return null
        const Icon = CATEGORY_ICONS[cat]
        const catStyle = CATEGORY_STYLE[cat]
        return (
          <div key={cat} className={`${styles.categoryGroup} ${catStyle}`}>
            <div className={styles.categoryHeader}>
              <div className={styles.categoryIcon}>
                <Icon size={24} />
              </div>
              <span className={styles.categoryName}>{t(categoryI18nKeys[cat])}</span>
              <span className={styles.categoryCount}>{list.length}</span>
            </div>
            <div className={styles.categoryDivider} />

            <m.div
              className={styles.cardGrid}
              variants={staggerContainerFast}
              initial="initial"
              animate="animate"
            >
              {list.map((src) => (
                <m.div
                  key={src.name}
                  variants={staggerItemSmall}
                  className={`${styles.sourceCard} ${!src.enabled ? styles.sourceCardDisabled : ''} ${statusBorderClass(src)}`}
                >
                  <StatusDot status={src.enabled ? src.status : 'disabled'} />

                  <div className={styles.cardBody}>
                    <div className={styles.sourceName}>{src.name}</div>
                    <div className={styles.badges}>
                      <TierBadge tier={src.tier} t={t} />
                      {src.required_key ? (
                        <span className={styles.configBadgeKey}>
                          <Key size={10} />
                          {t('sources.needsApiKey')}
                        </span>
                      ) : (
                        <span className={styles.configBadgeOk}>
                          <Check size={10} />
                          {t('sources.noConfigNeeded')}
                        </span>
                      )}
                    </div>
                    <div className={styles.cardDescription}>
                      {src.message}
                      {src.channel && Object.keys(src.channel).length > 0 && (
                        <span className={styles.channelInfo}>
                          [{Object.entries(src.channel).map(([k, v]) => `${k}=${v}`).join(', ')}]
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={styles.toggleArea}>
                    <button
                      className={`${styles.toggleBtn} ${src.enabled ? styles.toggleBtnEnabled : ''}`}
                      onClick={() => handleToggle(src)}
                      disabled={toggling === src.name}
                      title={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                      aria-label={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                    >
                      <span
                        className={`${styles.toggleKnob} ${src.enabled ? styles.toggleKnobEnabled : ''}`}
                      >
                        {src.enabled && <Check size={12} strokeWidth={3} />}
                      </span>
                    </button>
                  </div>
                </m.div>
              ))}
            </m.div>
          </div>
        )
      })}

      {/* Confirmation Modal */}
      <Modal
        open={!!confirmSource}
        onClose={() => setConfirmSource(null)}
        title={t('sources.confirmDisableTitle')}
        actions={
          <>
            <button className="btn btn-sm btn-outline" onClick={() => setConfirmSource(null)}>
              {t('common.cancel')}
            </button>
            <button className="btn btn-sm btn-danger" onClick={handleConfirmDisable}>
              {t('sources.confirmDisable')}
            </button>
          </>
        }
      >
        <p>{t('sources.confirmDisableMessage', { name: confirmSource?.name ?? '' })}</p>
      </Modal>
    </div>
  )
}
