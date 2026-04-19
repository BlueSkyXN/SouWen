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
 *     - 关键类型：CategoryKey 数据源类别（8 类）
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
import { RefreshCw, FileText, Shield, Globe, Key, AlertTriangle, Info, ChevronDown } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse, DoctorSource, SourceChannelConfig, WarpStatus } from '@core/types'
import styles from './SourcesPage.module.scss'

type CategoryKey = 'paper' | 'patent' | 'general' | 'professional' | 'social' | 'developer' | 'wiki' | 'video'

const CATEGORY_ORDER: CategoryKey[] = ['paper', 'patent', 'general', 'professional', 'social', 'developer', 'wiki', 'video']

const CATEGORY_ICONS: Record<CategoryKey, typeof FileText> = {
  paper: FileText,
  patent: Shield,
  general: Globe,
  professional: Globe,
  social: Globe,
  developer: Globe,
  wiki: Globe,
  video: Globe,
}

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  paper: 'sources.categoryPaper',
  patent: 'sources.categoryPatent',
  general: 'sources.categoryGeneral',
  professional: 'sources.categoryProfessional',
  social: 'sources.categorySocial',
  developer: 'sources.categoryDeveloper',
  wiki: 'sources.categoryWiki',
  video: 'sources.categoryVideo',
}

const CATEGORY_COLORS: Record<CategoryKey, string> = {
  paper: '#007aff',
  patent: '#ff9500',
  general: '#34c759',
  professional: '#5856d6',
  social: '#ff2d55',
  developer: '#af52de',
  wiki: '#007aff',
  video: '#ff3b30',
}

const PROXY_OPTIONS = ['inherit', 'none', 'warp', 'custom'] as const
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
          {t('sourceConfig.advancedTitle', 'Advanced Configuration')}
        </div>

        {/* Proxy */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>{t('sourceConfig.proxy', 'Proxy')}</label>
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
            <AlertTriangle size={12} />
            {t('sourceConfig.warpNotActive')}
          </div>
        )}

        {/* HTTP Backend */}
        <div className={styles.configRow}>
          <label className={styles.configLabel}>{t('sourceConfig.httpBackend', 'HTTP Backend')}</label>
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
          <label className={styles.configLabel}>{t('sourceConfig.baseUrl', 'Base URL')}</label>
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
          <label className={styles.configLabel}>{t('sourceConfig.apiKey', 'API Key')}</label>
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
                    {t('sourceConfig.set', 'Set')}
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
                <span className={styles.apiKeyClearLabel}>{t('sourceConfig.willClear', 'Will be cleared')}</span>
                <button className={styles.apiKeyBtn} onClick={() => setApiKeyAction('keep')}>
                  {t('common.undo', 'Undo')}
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
            {saving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
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
  const [warpStatus, setWarpStatus] = useState<WarpStatus | null>(null)
  const addToast = useNotificationStore((s) => s.addToast)

  // 获取数据源诊断和配置数据
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

  // 执行数据源启用/禁用切换
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
      <div className={styles.pageHeaderRow}>
        <h1 className={styles.pageTitle}>{t('sources.title', '数据源')}</h1>
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
              {list.map((src, i) => (
                <m.div key={src.name} variants={staggerItem}>
                  <div
                    className={`${styles.sourceRow} ${i < list.length - 1 ? styles.sourceRowSep : ''} ${!src.enabled ? styles.sourceRowDisabled : ''}`}
                  >
                    <div
                      className={styles.sourceMain}
                      onClick={() => setExpandedSource(expandedSource === src.name ? null : src.name)}
                      style={{ cursor: 'pointer' }}
                    >
                      <span className={styles.squircleIcon} style={{ background: CATEGORY_COLORS[cat] }}>
                        <Icon size={12} color="#fff" />
                      </span>
                      <div className={styles.sourceTextCol}>
                        <div className={styles.sourceNameRow}>
                          <span className={styles.sourceName}>{src.name}</span>
                          <ChevronDown
                            size={12}
                            className={`${styles.expandIcon} ${expandedSource === src.name ? styles.expandIconOpen : ''}`}
                          />
                        </div>
                        <div className={styles.sourceDesc}>{src.message}</div>
                      </div>
                    </div>
                    {/* iOS Toggle */}
                    <button
                      className={`${styles.iosToggle} ${src.enabled ? styles.iosToggleOn : ''}`}
                      onClick={() => handleToggle(src)}
                      disabled={toggling === src.name}
                      aria-label={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                    >
                      <span className={styles.iosToggleThumb} />
                    </button>
                  </div>

                  {src.required_key && expandedSource !== src.name && (
                    <div className={styles.authHint}>
                      <Key size={10} />
                      <code>{src.required_key}</code>
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
