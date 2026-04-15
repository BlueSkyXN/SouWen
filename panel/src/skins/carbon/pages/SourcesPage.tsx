import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import { Database, RefreshCw, FileText, Shield, Globe, Key } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse, DoctorSource } from '@core/types'
import styles from './SourcesPage.module.scss'

type CategoryKey = 'paper' | 'patent' | 'web'

const CATEGORY_ORDER: CategoryKey[] = ['paper', 'patent', 'web']

const CATEGORY_ICONS: Record<CategoryKey, typeof FileText> = {
  paper: FileText,
  patent: Shield,
  web: Globe,
}

const CATEGORY_BORDER: Record<CategoryKey, string> = {
  paper: styles.borderPaper,
  patent: styles.borderPatent,
  web: styles.borderWeb,
}

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  paper: 'sources.categoryPaper',
  patent: 'sources.categoryPatent',
  web: 'sources.categoryWeb',
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

  if (loading) {
    return <Spinner label={t('common.loading', 'Loading...')} />
  }

  if (fetchError || !doctor) {
    return (
      <div className={styles.errorState}>
        <p>{t('sources.errorDescription')}</p>
        <button className={styles.retryBtn} onClick={fetchData}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          {t('common.retry', 'Retry')}
        </button>
      </div>
    )
  }

  const sourcesByCategory: Record<string, DoctorSource[]> = {}
  for (const cat of CATEGORY_ORDER) {
    sourcesByCategory[cat] = doctor.sources.filter((s) => s.category === cat)
  }

  return (
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <Database size={20} />
          SOURCE.REGISTRY
        </h1>
        <button className={styles.syncBtn} onClick={fetchData}>
          <RefreshCw size={14} />
          FORCE SYNC
        </button>
      </div>

      {/* ── Category Groups ── */}
      {CATEGORY_ORDER.map((cat) => {
        const list = sourcesByCategory[cat]
        if (!list || list.length === 0) return null
        const Icon = CATEGORY_ICONS[cat]
        const borderClass = CATEGORY_BORDER[cat]

        return (
          <div key={cat} className={`${styles.categorySection} ${borderClass}`}>
            <div className={styles.categoryHeader}>
              <Icon size={16} />
              {t(CATEGORY_LABELS[cat])}
              <span className={styles.categoryCount}>({list.length})</span>
            </div>

            <m.div
              className={styles.cardGrid}
              variants={staggerContainer}
              initial="initial"
              animate="animate"
            >
              {list.map((src) => (
                <m.div
                  key={src.name}
                  variants={staggerItem}
                  className={`${styles.sourceCard} ${!src.enabled ? styles.sourceCardDisabled : ''}`}
                >
                  <div className={styles.cardTop}>
                    <div className={styles.sourceName}>{src.name}</div>
                    <div className={styles.cardBadges}>
                      <button
                        className={`${styles.toggleBadge} ${src.enabled ? styles.on : styles.off}`}
                        onClick={() => handleToggle(src)}
                        disabled={toggling === src.name}
                        title={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                      >
                        {src.enabled ? 'ON' : 'OFF'}
                      </button>
                      <span className={styles.tierBadge}>T{src.tier}</span>
                    </div>
                  </div>

                  <div className={styles.cardDesc}>{src.message}</div>

                  {src.required_key && (
                    <div className={styles.authInfo}>
                      <Key size={10} />
                      AUTH: <code className={styles.authKey}>{src.required_key}</code>
                    </div>
                  )}
                </m.div>
              ))}
            </m.div>
          </div>
        )
      })}

      {/* ── Confirmation Modal ── */}
      <AnimatePresence>
        {confirmSource && (
          <m.div
            className={styles.modalOverlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setConfirmSource(null)}
          >
            <m.div
              className={styles.modalCard}
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className={styles.modalTitle}>{t('sources.confirmDisableTitle')}</h3>
              <p className={styles.modalBody}>
                {t('sources.confirmDisableMessage', { name: confirmSource.name })}
              </p>
              <div className={styles.modalActions}>
                <button className={styles.modalBtn} onClick={() => setConfirmSource(null)}>
                  {t('common.cancel', 'Cancel')}
                </button>
                <button
                  className={`${styles.modalBtn} ${styles.modalBtnDanger}`}
                  onClick={handleConfirmDisable}
                >
                  {t('sources.confirmDisable')}
                </button>
              </div>
            </m.div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
