/**
 * 文件用途：Carbon 皮肤的数据源管理页面，管理各类别数据源的配置、密钥、代理和后端设置
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
import { Database, RefreshCw, FileText, Shield, Globe, Key, AlertTriangle, Info, ChevronDown } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import { SOURCE_CATEGORY_LABEL_KEYS, SOURCE_CATEGORY_ORDER } from '@core/types'
import type { DoctorResponse, DoctorSource, SourceCategory, SourceChannelConfig, WarpStatus } from '@core/types'
import styles from './SourcesPage.module.scss'

const CATEGORY_ORDER = SOURCE_CATEGORY_ORDER
const CATEGORY_LABELS = SOURCE_CATEGORY_LABEL_KEYS

const CATEGORY_ICONS: Record<SourceCategory, typeof FileText> = {
  paper: FileText,
  patent: Shield,
  general: Globe,
  professional: Globe,
  social: Globe,
  office: Globe,
  developer: Globe,
  wiki: Globe,
  cn_tech: Globe,
  video: Globe,
  fetch: Globe,
}

const CATEGORY_BORDER: Record<SourceCategory, string> = {
  paper: styles.borderPaper,
  patent: styles.borderPatent,
  general: styles.borderWeb,
  professional: styles.borderWeb,
  social: styles.borderWeb,
  office: styles.borderWeb,
  developer: styles.borderWeb,
  wiki: styles.borderWeb,
  cn_tech: styles.borderWeb,
  video: styles.borderWeb,
  fetch: styles.borderWeb,
}

const PROXY_OPTIONS = ['inherit', 'none', 'warp', 'custom'] as const
const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

const expandVariants = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1, transition: { duration: 0.25, ease: 'easeOut' as const } },
  exit: { height: 0, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' as const } },
}

/**
 * SourceConfigPanel 子组件 - 单个数据源的配置表单
 * @param {string} sourceName - 数据源名称
 * @param {SourceChannelConfig} config - 当前配置状态
 * @param {WarpStatus | null} warpStatus - WARP 代理状态
 * @param {() => void} onSaved - 保存成功后的回调函数
 */
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

  // 保存配置到服务器
  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const params: Record<string, string> = {
        proxy,
        http_backend: httpBackend,
        base_url: baseUrl || '',
      }
      // 处理 API 密钥操作：替换、清除或保留
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
          [{t('sourceConfig.advancedConfig')}]
        </div>

        {/* Proxy 代理设置 */}
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

        {/* HTTP Backend 后端选择 */}
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

        {/* Base URL 基础 URL */}
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

        {/* API Key 密钥管理，支持保留、替换或清除 */}
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
                    {t('sourceConfig.apiKeySetBtn')}
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
                <span className={styles.apiKeyClearLabel}>{t('sourceConfig.willClear', '将清除')}</span>
                <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('keep')}>
                  {t('sourceConfig.undo', '撤销')}
                </button>
              </>
            )}
          </div>
        </div>

        {/* 运行时说明 */}
        <div className={styles.runtimeNote}>
          <Info size={11} />
          {t('sourceConfig.runtimeNote')}
        </div>

        {/* 保存配置按钮 */}
        <div className={styles.configActions}>
          <button
            className={styles.commitBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? '...' : t('sourceConfig.commit', '提交')}
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

  // 异步获取数据源诊断数据和配置
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

  // 单独获取 WARP 状态（可能不可用）
  useEffect(() => {
    api.getWarpStatus().then(setWarpStatus).catch(() => setWarpStatus(null))
  }, [])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  // 执行启用/禁用数据源操作
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

  // 处理数据源状态切换：已启用的数据源需要确认后才能禁用
  const handleToggle = useCallback((src: DoctorSource) => {
    if (src.enabled && src.status === 'ok') {
      setConfirmSource(src)
    } else {
      void executeToggle(src.name, src.enabled)
    }
  }, [executeToggle])

  // 确认禁用数据源
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

  // 按类别对数据源进行分组
  const sourcesByCategory: Record<string, DoctorSource[]> = {}
  const statusOrder: Record<string, number> = {
    ok: 0,
    limited: 1,
    warning: 2,
    degraded: 2,
    missing_key: 3,
    needs_key: 3,
    unavailable: 4,
    error: 5,
    timeout: 6,
    disabled: 7,
  }
  for (const cat of CATEGORY_ORDER) {
    sourcesByCategory[cat] = doctor.sources
      .filter((s) => s.category === cat)
      .sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
        const diff = (statusOrder[a.status] ?? 5) - (statusOrder[b.status] ?? 5)
        return diff !== 0 ? diff : a.name.localeCompare(b.name)
      })
  }

  return (
    <div className={styles.page}>
      {/* ── Header 页面头部 ── */}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>
          <Database size={20} />
          {t('sources.pageTitle', '数据源管理')}
        </h1>
        <button className={styles.syncBtn} onClick={fetchData}>
          <RefreshCw size={14} />
          {t('sources.refresh', '刷新')}
        </button>
      </div>

      {/* ── Category Groups 按类别分组展示数据源 ── */}
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
              {list.map((src: DoctorSource) => (
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
                        {src.enabled ? t('sources.on', '开') : t('sources.off', '关')}
                      </button>
                      <span className={styles.tierBadge}>{src.integration_type === 'open_api' ? '开放' : src.integration_type === 'scraper' ? '爬虫' : src.integration_type === 'official_api' ? '授权' : '自建'}</span>
                    </div>
                  </div>

                  <div className={styles.cardDesc}>{src.message}</div>

                  {src.required_key && (
                    <div className={styles.authInfo}>
                      <Key size={10} />
                      {t('sources.auth', '认证')}: <code className={styles.authKey}>{src.required_key}</code>
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

      {/* ── Confirmation Modal 禁用确认对话框 ── */}
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
