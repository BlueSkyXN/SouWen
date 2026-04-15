import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  RefreshCw, FileText, Shield, Globe, Key, Star, Check, Sparkles, Zap,
  ChevronDown, AlertTriangle, Save, Info, X,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { Modal } from '../components/common/Modal'
import { EmptyState } from '../components/common/EmptyState'
import { Skeleton } from '../components/common/Skeleton'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Input } from '../components/common/Input'
import { formatError } from '@core/lib/errors'
import { staggerContainerFast, staggerItemSmall } from '@core/lib/animations'

import type { DoctorResponse, DoctorSource, SourceChannelConfig } from '@core/types'
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

const expandVariants = {
  collapsed: { height: 0, opacity: 0 },
  expanded: { height: 'auto', opacity: 1 },
}

const expandTransition = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 34,
  mass: 0.8,
}

const PROXY_OPTIONS = ['inherit', 'none', 'warp', 'custom'] as const
const HTTP_BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

function SourceConfigPanel({
  sourceName,
  config,
  onSaved,
}: {
  sourceName: string
  config: SourceChannelConfig
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)

  // Determine initial proxy mode
  const getProxyMode = (val: string) => {
    if (val === 'inherit' || val === '') return 'inherit'
    if (val === 'none') return 'none'
    if (val === 'warp') return 'warp'
    return 'custom'
  }

  const [proxyMode, setProxyMode] = useState<string>(getProxyMode(config.proxy))
  const [customProxy, setCustomProxy] = useState(getProxyMode(config.proxy) === 'custom' ? config.proxy : '')
  const [httpBackend, setHttpBackend] = useState(config.http_backend || 'auto')
  const [baseUrl, setBaseUrl] = useState(config.base_url || '')
  const [hasApiKey, setHasApiKey] = useState(config.has_api_key)
  const [apiKeyMode, setApiKeyMode] = useState<'view' | 'replace'>('view')
  const [newApiKey, setNewApiKey] = useState('')
  const [clearApiKey, setClearApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [warpWarning, setWarpWarning] = useState(false)

  // Check WARP status when proxy=warp is selected
  const checkWarpStatus = useCallback(async () => {
    try {
      const status = await api.getWarpStatus()
      setWarpWarning(status.status !== 'enabled')
    } catch {
      setWarpWarning(true)
    }
  }, [])

  useEffect(() => {
    if (proxyMode === 'warp') {
      void checkWarpStatus()
    } else {
      setWarpWarning(false)
    }
  }, [proxyMode, checkWarpStatus])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const params: Record<string, string | undefined> = {}

      // Proxy
      if (proxyMode === 'inherit') params.proxy = 'inherit'
      else if (proxyMode === 'none') params.proxy = 'none'
      else if (proxyMode === 'warp') params.proxy = 'warp'
      else if (proxyMode === 'custom') params.proxy = customProxy

      // HTTP backend (only for scrapers)
      if (config.is_scraper) {
        params.http_backend = httpBackend
      }

      // Base URL
      params.base_url = baseUrl || ''

      // API key — only include if user explicitly changed it
      if (clearApiKey) {
        params.api_key = ''
      } else if (apiKeyMode === 'replace' && newApiKey) {
        params.api_key = newApiKey
      }

      await api.updateSourceConfig(sourceName, params)
      addToast('success', t('sourceConfig.saveSuccess'))

      // Update local state for api key display
      if (clearApiKey) {
        setHasApiKey(false)
        setClearApiKey(false)
      } else if (apiKeyMode === 'replace' && newApiKey) {
        setHasApiKey(true)
        setNewApiKey('')
      }
      setApiKeyMode('view')
      onSaved()
    } catch (err) {
      addToast('error', t('sourceConfig.saveFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [proxyMode, customProxy, httpBackend, baseUrl, clearApiKey, apiKeyMode, newApiKey, sourceName, config.is_scraper, addToast, t, onSaved])

  const handleClearApiKey = useCallback(() => {
    if (window.confirm(t('sourceConfig.apiKeyConfirmClear'))) {
      setClearApiKey(true)
      setApiKeyMode('view')
      setNewApiKey('')
    }
  }, [t])

  return (
    <div className={styles.configPanel}>
      <div className={styles.configPanelNote}>
        <Info size={14} />
        <span>{t('sourceConfig.runtimeNote')}</span>
      </div>

      <div className={styles.configForm}>
        {/* Proxy */}
        <div className={styles.configField}>
          <label className={styles.configLabel}>{t('sourceConfig.proxy')}</label>
          <select
            className={styles.configSelect}
            value={proxyMode}
            onChange={(e) => {
              setProxyMode(e.target.value)
              if (e.target.value !== 'custom') setCustomProxy('')
            }}
          >
            <option value="inherit">{t('sourceConfig.proxyInherit')}</option>
            <option value="none">{t('sourceConfig.proxyNone')}</option>
            <option value="warp">{t('sourceConfig.proxyWarp')}</option>
            <option value="custom">{t('sourceConfig.proxyCustom')}</option>
          </select>
          {proxyMode === 'custom' && (
            <Input
              type="text"
              value={customProxy}
              onChange={(e) => setCustomProxy(e.target.value)}
              placeholder="socks5://127.0.0.1:1080"
            />
          )}
          {warpWarning && (
            <div className={styles.warpWarning}>
              <AlertTriangle size={14} />
              <span>{t('sourceConfig.warpNotActive')}</span>
            </div>
          )}
        </div>

        {/* HTTP Backend — only for scrapers */}
        {config.is_scraper && (
          <div className={styles.configField}>
            <label className={styles.configLabel}>{t('sourceConfig.httpBackend')}</label>
            <p className={styles.configFieldDesc}>{t('sourceConfig.httpBackendDesc')}</p>
            <select
              className={styles.configSelect}
              value={httpBackend}
              onChange={(e) => setHttpBackend(e.target.value)}
            >
              {HTTP_BACKEND_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>
        )}

        {/* Base URL */}
        <div className={styles.configField}>
          <label className={styles.configLabel}>{t('sourceConfig.baseUrl')}</label>
          <Input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={t('sourceConfig.baseUrlPlaceholder')}
          />
        </div>

        {/* API Key */}
        <div className={styles.configField}>
          <label className={styles.configLabel}>{t('sourceConfig.apiKey')}</label>
          <div className={styles.apiKeyRow}>
            {clearApiKey ? (
              <Badge color="red">{t('sourceConfig.apiKeyNotSet')}</Badge>
            ) : hasApiKey ? (
              <Badge color="green">{t('sourceConfig.apiKeySet')}</Badge>
            ) : (
              <Badge color="gray">{t('sourceConfig.apiKeyNotSet')}</Badge>
            )}
            {apiKeyMode === 'view' ? (
              <div className={styles.apiKeyActions}>
                <button
                  className={styles.apiKeyBtn}
                  onClick={() => { setApiKeyMode('replace'); setClearApiKey(false) }}
                >
                  {t('sourceConfig.apiKeyReplace')}
                </button>
                {hasApiKey && !clearApiKey && (
                  <button
                    className={`${styles.apiKeyBtn} ${styles.apiKeyBtnDanger}`}
                    onClick={handleClearApiKey}
                  >
                    {t('sourceConfig.apiKeyClear')}
                  </button>
                )}
              </div>
            ) : (
              <div className={styles.apiKeyInputRow}>
                <Input
                  type="password"
                  value={newApiKey}
                  onChange={(e) => setNewApiKey(e.target.value)}
                  placeholder={t('sourceConfig.apiKeyPlaceholder')}
                />
                <button
                  className={styles.apiKeyCancelBtn}
                  onClick={() => { setApiKeyMode('view'); setNewApiKey('') }}
                  aria-label="Cancel"
                >
                  <X size={14} />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.configPanelActions}>
        <Button
          variant="primary"
          size="sm"
          loading={saving}
          icon={<Save size={14} />}
          onClick={handleSave}
        >
          {t('common.save', 'Save')}
        </Button>
      </div>
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
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [sourcesConfig, setSourcesConfig] = useState<Record<string, SourceChannelConfig>>({})
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchSourcesConfig = useCallback(async () => {
    try {
      const cfg = await api.getSourcesConfig()
      setSourcesConfig(cfg)
    } catch {
      // non-critical, config panel will just show defaults
    }
  }, [])

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
    void fetchSourcesConfig()
  }, [fetchData, fetchSourcesConfig])

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

  const handleCardClick = useCallback((sourceName: string) => {
    setExpandedSource((prev) => prev === sourceName ? null : sourceName)
  }, [])

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
                  className={`${styles.sourceCard} ${!src.enabled ? styles.sourceCardDisabled : ''} ${statusBorderClass(src)} ${expandedSource === src.name ? styles.sourceCardExpanded : ''}`}
                >
                  <div className={styles.sourceCardTop} onClick={() => handleCardClick(src.name)}>
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

                    <div className={styles.cardActions}>
                      <span className={`${styles.expandIcon} ${expandedSource === src.name ? styles.expandIconOpen : ''}`}>
                        <ChevronDown size={16} />
                      </span>
                      <div className={styles.toggleArea} onClick={(e) => e.stopPropagation()}>
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
                    </div>
                  </div>

                  <AnimatePresence initial={false}>
                    {expandedSource === src.name && sourcesConfig[src.name] && (
                      <m.div
                        variants={expandVariants}
                        initial="collapsed"
                        animate="expanded"
                        exit="collapsed"
                        transition={expandTransition}
                        style={{ overflow: 'hidden' }}
                      >
                        <SourceConfigPanel
                          sourceName={src.name}
                          config={sourcesConfig[src.name]}
                          onSaved={() => void fetchSourcesConfig()}
                        />
                      </m.div>
                    )}
                  </AnimatePresence>
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
