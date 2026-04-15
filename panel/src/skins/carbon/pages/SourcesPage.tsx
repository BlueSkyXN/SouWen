import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import { Database, RefreshCw, FileText, Shield, Globe, Key, AlertTriangle, Info, ChevronDown } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse, DoctorSource, SourceChannelConfig, WarpStatus } from '@core/types'
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

const PROXY_OPTIONS = ['inherit', 'none', 'warp', 'custom'] as const
const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

const expandVariants = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1, transition: { duration: 0.25, ease: 'easeOut' as const } },
  exit: { height: 0, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' as const } },
}

function SourceConfigPanel({
  sourceName,
  config,
  warpStatus,
  onSaved,
}: {
  sourceName: string
  config: SourceChannelConfig
  warpStatus: WarpStatus | null
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [proxy, setProxy] = useState(config.proxy || 'inherit')
  const [httpBackend, setHttpBackend] = useState(config.http_backend || 'auto')
  const [baseUrl, setBaseUrl] = useState(config.base_url || '')
  const [apiKeyAction, setApiKeyAction] = useState<'keep' | 'replace' | 'clear'>('keep')
  const [apiKeyValue, setApiKeyValue] = useState('')
  const [saving, setSaving] = useState(false)

  const warpActive = warpStatus?.status === 'enabled'
  const showWarpWarning = proxy === 'warp' && !warpActive

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const params: Record<string, string> = {
        proxy,
        http_backend: httpBackend,
        base_url: baseUrl || '',
      }
      if (apiKeyAction === 'replace' && apiKeyValue) {
        params.api_key = apiKeyValue
      } else if (apiKeyAction === 'clear') {
        params.api_key = ''
      }
      await api.updateSourceConfig(sourceName, params)
      addToast('success', t('sourceConfig.saveSuccess', { name: sourceName }))
      onSaved()
    } catch (err) {
      addToast('error', t('sourceConfig.saveFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [sourceName, proxy, httpBackend, baseUrl, apiKeyAction, apiKeyValue, addToast, t, onSaved])

  return (
    <m.div
      className={styles.configPanel}
      variants={expandVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div className={styles.configPanelInner}>
        <div className={styles.configPanelHeader}>
          [ADVANCED_CONFIG]
        </div>

        {/* Proxy */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>proxy</label>
          <span className={styles.configSep}>──────</span>
          <select
            className={styles.configSelect}
            value={proxy}
            onChange={(e) => setProxy(e.target.value)}
          >
            {PROXY_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{t(`sourceConfig.proxy${opt.charAt(0).toUpperCase() + opt.slice(1)}`)}</option>
            ))}
          </select>
        </div>
        {showWarpWarning && (
          <div className={styles.warpWarning}>
            <AlertTriangle size={11} />
            {t('sourceConfig.warpNotActive')}
          </div>
        )}

        {/* HTTP Backend */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>http_backend</label>
          <span className={styles.configSep}>─</span>
          <select
            className={styles.configSelect}
            value={httpBackend}
            onChange={(e) => setHttpBackend(e.target.value)}
          >
            {BACKEND_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>

        {/* Base URL */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>base_url</label>
          <span className={styles.configSep}>─────</span>
          <input
            className={styles.configInput}
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={t('sourceConfig.baseUrlPlaceholder')}
          />
        </div>

        {/* API Key */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>api_key</label>
          <span className={styles.configSep}>──────</span>
          <div className={styles.apiKeyGroup}>
            {apiKeyAction === 'keep' && (
              <>
                <span className={`${styles.apiKeyStatus} ${config.has_api_key ? styles.apiKeySet : styles.apiKeyUnset}`}>
                  ● {config.has_api_key ? t('sourceConfig.apiKeySet') : t('sourceConfig.apiKeyNotSet')}
                </span>
                {config.has_api_key && (
                  <>
                    <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('replace')}>
                      {t('sourceConfig.apiKeyReplace')}
                    </button>
                    <button className={`${styles.apiKeyBtn} ${styles.apiKeyBtnClear}`} onClick={() => setApiKeyAction('clear')}>
                      {t('sourceConfig.apiKeyClear')}
                    </button>
                  </>
                )}
                {!config.has_api_key && (
                  <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('replace')}>
                    SET
                  </button>
                )}
              </>
            )}
            {apiKeyAction === 'replace' && (
              <>
                <input
                  className={styles.configInput}
                  type="password"
                  value={apiKeyValue}
                  onChange={(e) => setApiKeyValue(e.target.value)}
                  placeholder={t('sourceConfig.apiKeyPlaceholder')}
                  autoFocus
                />
                <button className={styles.apiKeyBtn} onClick={() => { setApiKeyAction('keep'); setApiKeyValue('') }}>
                  ✕
                </button>
              </>
            )}
            {apiKeyAction === 'clear' && (
              <>
                <span className={styles.apiKeyClearLabel}>WILL CLEAR</span>
                <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('keep')}>
                  UNDO
                </button>
              </>
            )}
          </div>
        </div>

        {/* Runtime note */}
        <div className={styles.runtimeNote}>
          <Info size={11} />
          {t('sourceConfig.runtimeNote')}
        </div>

        {/* Save button */}
        <div className={styles.configActions}>
          <button
            className={styles.commitBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? '...' : 'COMMIT'}
          </button>
        </div>
      </div>
    </m.div>
  )
}

export function SourcesPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [confirmSource, setConfirmSource] = useState<DoctorSource | null>(null)
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [sourcesConfig, setSourcesConfig] = useState<Record<string, SourceChannelConfig>>({})
  const [warpStatus, setWarpStatus] = useState<WarpStatus | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setFetchError(false)
    try {
      const [d, sc] = await Promise.all([
        api.getDoctor(),
        api.getSourcesConfig(),
      ])
      setDoctor(d)
      setSourcesConfig(sc)
    } catch (err) {
      setFetchError(true)
      addToast('error', t('sources.fetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  // Fetch WARP status separately (may not be available)
  useEffect(() => {
    api.getWarpStatus().then(setWarpStatus).catch(() => setWarpStatus(null))
  }, [])

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
                  className={`${styles.sourceCard} ${!src.enabled ? styles.sourceCardDisabled : ''} ${expandedSource === src.name ? styles.sourceCardExpanded : ''}`}
                >
                  <div
                    className={styles.cardTop}
                    onClick={() => setExpandedSource(expandedSource === src.name ? null : src.name)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className={styles.sourceNameRow}>
                      <ChevronDown
                        size={12}
                        className={`${styles.expandIcon} ${expandedSource === src.name ? styles.expandIconOpen : ''}`}
                      />
                      <div className={styles.sourceName}>{src.name}</div>
                    </div>
                    <div className={styles.cardBadges}>
                      <button
                        className={`${styles.toggleBadge} ${src.enabled ? styles.on : styles.off}`}
                        onClick={(e) => { e.stopPropagation(); handleToggle(src) }}
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

                  <AnimatePresence>
                    {expandedSource === src.name && sourcesConfig[src.name] && (
                      <SourceConfigPanel
                        sourceName={src.name}
                        config={sourcesConfig[src.name]}
                        warpStatus={warpStatus}
                        onSaved={fetchData}
                      />
                    )}
                  </AnimatePresence>
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
