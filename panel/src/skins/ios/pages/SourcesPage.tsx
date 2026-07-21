/**
 * 文件用途：iOS 皮肤的数据源管理页面，管理各类别数据源的配置、密钥、代理和后端设置
 *
 * 组件/函数清单：
 *   SourcesPage（函数组件）
 *     - 功能：按类别（论文、专利、网页）展示和配置数据源
 *       1. 获取服务器诊断数据中的所有数据源列表
 *       2. 为每个数据源显示配置面板，支持修改代理、HTTP 后端、基础 URL、API 密钥
 *       3. 支持保存配置到服务器
 *     - State 状态：doctor (DoctorResponse) 包含所有数据源信息, loading/error 状态
 *     - 关键类型：SourceCategory 数据源类别（11 类）
 *     - 关键钩子：useTranslation, useNotificationStore
 *
 *   SourceConfigPanel（子组件）
 *     - 功能：单个数据源的配置表单，支持修改代理、HTTP 后端、密钥等
 *     - Props 属性：sourceName 数据源名称, config 当前配置, warpStatus WARP 状态, onSaved 保存回调
 *     - 关键状态：apiKeyAction ('keep'|'replace'|'clear') 密钥操作方式
 *
 * 模块依赖：
 *   - react: 状态和表单
 *   - react-i18next: 翻译
 *   - framer-motion: 展开/收起动画
 *   - lucide-react: 图标
 *   - @core/services/api: 获取/保存配置
 *   - SourcesPage.module.scss: 样式
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import { RefreshCw, BookOpen, FileText, Shield, Globe, Key, AlertTriangle, Info, ChevronDown } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { useAuthStore } from '@core/stores/authStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { hasFeatureAccess } from '@core/lib/access'
import {
  doctorStatusOrder,
  isDoctorStatusAvailable,
  sourceAvailabilitySummary,
  sourceCredentialLabel,
} from '@core/lib/sourceStatus'
import { shouldSubmitConfigValue } from '@core/lib/redactedConfig'
import {
  SOURCE_CUSTOM_PROXY_EXAMPLE,
  SOURCE_PROXY_MODES,
  getSourceCustomProxyValue,
  getSourceProxyMode,
  getSourceProxyValue,
  type SourceProxyMode,
} from '@core/lib/sourceProxyConfig'
import { Spinner } from '../components/common/Spinner'
import { SOURCE_CATEGORY_LABEL_KEYS, SOURCE_CATEGORY_ORDER } from '@core/types'
import type { DoctorResponse, DoctorSource, SourceCategory, SourceChannelConfig, SourceInfo, WarpStatus } from '@core/types'
import styles from './SourcesPage.module.scss'

const CATEGORY_ORDER = SOURCE_CATEGORY_ORDER
const CATEGORY_LABELS = SOURCE_CATEGORY_LABEL_KEYS

const CATEGORY_ICONS: Record<SourceCategory, typeof FileText> = {
  book: BookOpen,
  paper: FileText,
  research_output: FileText,
  patent: Shield,
  web_general: Globe,
  web_professional: Globe,
  social: Globe,
  office: Globe,
  developer: Globe,
  knowledge: Globe,
  cn_tech: Globe,
  video: Globe,
  archive: Globe,
  fetch: Globe,
}

const CATEGORY_COLORS: Record<SourceCategory, string> = {
  book: '#007aff',
  paper: '#007aff',
  research_output: '#5856d6',
  patent: '#ff9500',
  web_general: '#34c759',
  web_professional: '#5856d6',
  social: '#ff2d55',
  office: '#30b0c7',
  developer: '#af52de',
  knowledge: '#007aff',
  cn_tech: '#32ade6',
  video: '#ff3b30',
  archive: '#ff9f0a',
  fetch: '#ff9f0a',
}

const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

const expandVariants = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1, transition: { duration: 0.25, ease: 'easeOut' as const } },
  exit: { height: 0, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' as const } },
}

// 数据源配置子组件
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
  const [initialProxy, setInitialProxy] = useState(config.proxy || 'inherit')
  const [proxyMode, setProxyMode] = useState<SourceProxyMode>(getSourceProxyMode(initialProxy))
  const [customProxy, setCustomProxy] = useState(getSourceCustomProxyValue(initialProxy))
  const [httpBackend, setHttpBackend] = useState(config.http_backend || 'auto')
  const [baseUrl, setBaseUrl] = useState(config.base_url || '')
  const [initialBaseUrl, setInitialBaseUrl] = useState(config.base_url || '')
  const [apiKeyAction, setApiKeyAction] = useState<'keep' | 'replace' | 'clear'>('keep')
  const [apiKeyValue, setApiKeyValue] = useState('')
  const [saving, setSaving] = useState(false)

  const warpActive = warpStatus?.status === 'enabled'
  const showWarpWarning = proxyMode === 'warp' && !warpActive

  useEffect(() => {
    const nextProxy = config.proxy || 'inherit'
    const nextBaseUrl = config.base_url || ''
    setInitialProxy(nextProxy)
    setProxyMode(getSourceProxyMode(nextProxy))
    setCustomProxy(getSourceCustomProxyValue(nextProxy))
    setHttpBackend(config.http_backend || 'auto')
    setBaseUrl(nextBaseUrl)
    setInitialBaseUrl(nextBaseUrl)
    setApiKeyAction('keep')
    setApiKeyValue('')
  }, [sourceName, config.proxy, config.http_backend, config.base_url, config.has_api_key])

  // 保存配置到服务器
  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const params: Record<string, string> = {
        http_backend: httpBackend,
      }
      const nextProxy = getSourceProxyValue(proxyMode, customProxy)
      if (shouldSubmitConfigValue(nextProxy, initialProxy)) params.proxy = nextProxy
      if (shouldSubmitConfigValue(baseUrl, initialBaseUrl)) params.base_url = baseUrl || ''
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
  }, [sourceName, proxyMode, customProxy, initialProxy, httpBackend, baseUrl, initialBaseUrl, apiKeyAction, apiKeyValue, addToast, t, onSaved])

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
          {t('sourceConfig.advancedTitle')}
        </div>

        {/* Proxy */}
        <div className={styles.configRow}>
          <label className={styles.configLabel} htmlFor={`source-${sourceName}-proxy-mode`}>{t('sourceConfig.proxy')}</label>
          <select
            id={`source-${sourceName}-proxy-mode`}
            className={styles.configSelect}
            value={proxyMode}
            onChange={(e) => {
              const mode = e.target.value as SourceProxyMode
              setProxyMode(mode)
              if (mode !== 'custom') setCustomProxy('')
            }}
          >
            {SOURCE_PROXY_MODES.map((opt) => (
              <option key={opt} value={opt}>{t(`sourceConfig.proxy${opt.charAt(0).toUpperCase() + opt.slice(1)}`)}</option>
            ))}
          </select>
        </div>
        {proxyMode === 'custom' && (
          <div className={styles.configRow}>
            <label className={styles.configLabel} htmlFor={`source-${sourceName}-custom-proxy`}>{t('sourceConfig.proxyCustom')}</label>
            <input
              id={`source-${sourceName}-custom-proxy`}
              className={styles.configInput}
              type="text"
              value={customProxy}
              onChange={(e) => setCustomProxy(e.target.value)}
              placeholder={t('sourceConfig.proxyCustomPlaceholder', { example: SOURCE_CUSTOM_PROXY_EXAMPLE })}
            />
          </div>
        )}
        {showWarpWarning && (
          <div className={styles.warpWarning}>
            <AlertTriangle size={12} />
            {t('sourceConfig.warpNotActive')}
          </div>
        )}

        {/* HTTP Backend */}
        <div className={styles.configRow}>
          <label className={styles.configLabel} htmlFor={`source-${sourceName}-http-backend`}>{t('sourceConfig.httpBackend')}</label>
          <select
            id={`source-${sourceName}-http-backend`}
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
          <label className={styles.configLabel} htmlFor={`source-${sourceName}-base-url`}>{t('sourceConfig.baseUrl')}</label>
          <input
            id={`source-${sourceName}-base-url`}
            className={styles.configInput}
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={t('sourceConfig.baseUrlPlaceholder')}
          />
        </div>

        {/* API Key */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>{t('sourceConfig.apiKey')}</label>
          <div className={styles.apiKeyGroup}>
            {apiKeyAction === 'keep' && (
              <>
                <span className={`${styles.apiKeyStatus} ${config.has_api_key ? styles.apiKeySet : styles.apiKeyUnset}`}>
                  <span className={styles.apiKeyDot} />
                  {config.has_api_key ? t('sourceConfig.apiKeySet') : t('sourceConfig.apiKeyNotSet')}
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
                    {t('sourceConfig.set')}
                  </button>
                )}
              </>
            )}
            {apiKeyAction === 'replace' && (
              <>
                <input
                  aria-label={t('sourceConfig.apiKey')}
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
                <span className={styles.apiKeyClearLabel}>{t('sourceConfig.willClear')}</span>
                <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('keep')}>
                  {t('common.undo')}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Runtime note */}
        <div className={styles.runtimeNote}>
          <Info size={12} />
          {t('sourceConfig.runtimeNote')}
        </div>

        {/* Save button */}
        <div className={styles.configActions}>
          <button
            className={styles.saveBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </div>
    </m.div>
  )
}

// SourcesPage 组件 - 数据源管理主组件
export function SourcesPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [confirmSource, setConfirmSource] = useState<DoctorSource | null>(null)
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [sourcesConfig, setSourcesConfig] = useState<Record<string, SourceChannelConfig>>({})
  const [sourceCatalog, setSourceCatalog] = useState<Record<string, SourceInfo>>({})
  const [warpStatus, setWarpStatus] = useState<WarpStatus | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)
  const features = useAuthStore((s) => s.features)
  const role = useAuthStore((s) => s.role)
  const canWriteSources = hasFeatureAccess(features, role, 'sources_config_write')

  // 获取数据源诊断和配置数据
  const fetchData = useCallback(async () => {
    setLoading(true)
    setFetchError(false)
    try {
      const [d, catalog] = await Promise.all([
        api.getDoctor(),
        api.getSources().catch(() => null),
      ])
      setDoctor(d)
      setSourceCatalog(Object.fromEntries(
        (catalog?.sources ?? []).map((source) => [source.name, source]),
      ))
      if (canWriteSources) {
        setSourcesConfig(await api.getSourcesConfig())
      } else {
        setSourcesConfig({})
      }
    } catch (err) {
      setFetchError(true)
      addToast('error', t('sources.fetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, canWriteSources, t])

  // 单独获取 WARP 状态（可能不可用）
  useEffect(() => {
    if (!canWriteSources) {
      setWarpStatus(null)
      return
    }
    api.getWarpStatus().then(setWarpStatus).catch(() => setWarpStatus(null))
  }, [canWriteSources])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  // 执行数据源启用/禁用切换
  const executeToggle = useCallback(async (name: string, currentEnabled: boolean) => {
    if (!canWriteSources) return
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
  }, [canWriteSources, fetchData, addToast, t])

  const handleToggle = useCallback((src: DoctorSource) => {
    if (!canWriteSources) return
    if (src.enabled && isDoctorStatusAvailable(src.status)) {
      setConfirmSource(src)
    } else {
      void executeToggle(src.name, src.enabled)
    }
  }, [canWriteSources, executeToggle])

  const handleConfirmDisable = useCallback(() => {
    if (!confirmSource) return
    void executeToggle(confirmSource.name, confirmSource.enabled)
    setConfirmSource(null)
  }, [confirmSource, executeToggle])

  const getAvailability = useCallback((src: DoctorSource) => (
    sourceAvailabilitySummary({ ...src, ...(sourceCatalog[src.name] ?? {}) }, t)
  ), [sourceCatalog, t])

  if (loading) {
    return <Spinner label={t('common.loading')} />
  }

  if (fetchError || !doctor) {
    return (
      <div className={styles.errorState}>
        <p>{t('sources.errorDescription')}</p>
        <button className={styles.retryBtn} onClick={fetchData}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          {t('common.retry')}
        </button>
      </div>
    )
  }

  const sourcesByCategory: Record<string, DoctorSource[]> = {}
  for (const cat of CATEGORY_ORDER) {
    sourcesByCategory[cat] = doctor.sources
      .filter((s) => s.category === cat)
      .sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
        const diff = doctorStatusOrder(a.status) - doctorStatusOrder(b.status)
        return diff !== 0 ? diff : a.name.localeCompare(b.name)
      })
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeaderRow}>
        <h1 className={styles.pageTitle}>{t('sources.title')}</h1>
        <button className={styles.refreshBtn} onClick={fetchData}>
          <RefreshCw size={14} />
        </button>
      </div>

      {/* ── Category Groups ── */}
      {CATEGORY_ORDER.map((cat) => {
        const list = sourcesByCategory[cat]
        if (!list || list.length === 0) return null
        const Icon = CATEGORY_ICONS[cat]

        return (
          <div key={cat} className={styles.formGroup}>
            <div className={styles.groupTitle}>{t(CATEGORY_LABELS[cat])}</div>
            <m.div
              className={styles.groupCard}
              variants={staggerContainer}
              initial="initial"
              animate="animate"
            >
              {list.map((src, i) => {
                const availability = getAvailability(src)
                const expanded = expandedSource === src.name
                return (
                  <m.div key={src.name} variants={staggerItem}>
                  <div
                    className={`${styles.sourceRow} ${i < list.length - 1 ? styles.sourceRowSep : ''} ${!src.enabled ? styles.sourceRowDisabled : ''}`}
                  >
                    <button
                      type="button"
                      className={styles.sourceMain}
                      onClick={() => setExpandedSource(expanded ? null : src.name)}
                      aria-expanded={expanded}
                      aria-label={t(expanded ? 'sources.collapseSource' : 'sources.expandSource', { name: src.name })}
                    >
                      <span className={styles.squircleIcon} style={{ background: CATEGORY_COLORS[cat] }}>
                        <Icon size={12} color="#fff" />
                      </span>
                      <div className={styles.sourceTextCol}>
                        <div className={styles.sourceNameRow}>
                          <span className={styles.sourceName}>{src.name}</span>
                          <ChevronDown
                            size={12}
                            className={`${styles.expandIcon} ${expanded ? styles.expandIconOpen : ''}`}
                            aria-hidden="true"
                          />
                        </div>
                        <div className={styles.sourceDesc}>
                          {availability.label} · {availability.message}
                        </div>
                      </div>
                    </button>
                    {/* iOS Toggle */}
                    <button
                      type="button"
                      className={`${styles.iosToggle} ${src.enabled ? styles.iosToggleOn : ''}`}
                      onClick={() => handleToggle(src)}
                      disabled={!canWriteSources || toggling === src.name}
                      aria-label={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                      title={!canWriteSources ? t('sourceConfig.readOnly') : undefined}
                    >
                      <span className={styles.iosToggleThumb} />
                    </button>
                  </div>

                  {sourceCredentialLabel(src) && !expanded && (
                    <div className={styles.authHint}>
                      <Key size={10} />
                      <code>{sourceCredentialLabel(src)}</code>
                    </div>
                  )}

                  <AnimatePresence>
                    {canWriteSources && expanded && sourcesConfig[src.name] && (
                      <SourceConfigPanel
                        sourceName={src.name}
                        config={sourcesConfig[src.name]}
                        warpStatus={warpStatus}
                        onSaved={fetchData}
                      />
                    )}
                  </AnimatePresence>
                  </m.div>
                )
              })}
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
                <button type="button" className={styles.modalBtn} onClick={() => setConfirmSource(null)}>
                  {t('common.cancel')}
                </button>
                <button
                  type="button"
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
