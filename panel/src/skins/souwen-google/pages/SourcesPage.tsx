/**
 * 数据源页面 - 源的配置和健康状态管理
 *
 * 文件用途：展示所有数据源（8 类），显示源的状态、配置信息、API 密钥需求，
 * 支持启用/禁用源以及编辑配置（如 API 密钥）
 *
 * 核心功能：
 *   - 源分类展示：按 8 类分组显示
 *   - 状态徽章：ok / needs_key / error / disabled
 *   - 源信息卡片：名称、描述、层级（core/extended/experimental）
 *   - 配置编辑：弹窗编辑 API 密钥和其他源配置
 *   - 启用/禁用：切换源的启用状态
 *   - 实时反馈：配置更新成功/失败提示
 *
 * 类型与常量：
 *   CategoryKey - 搜索类别（8 类）
 *   CATEGORY_ORDER / CATEGORY_ICONS / CATEGORY_STYLE - 分类配置
 *   statusBorderClass / StatusDot / TierBadge - 状态显示组件
 *
 * 主要交互：
 *   - 页面加载时获取所有源和诊断信息
 *   - 点击源卡片打开编辑模态窗口
 *   - 编辑并保存配置
 *   - 切换源的启用/禁用状态
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  RefreshCw, FileText, Shield, Globe, Key, Star, Check, Sparkles, Zap, Server,
  ChevronDown, AlertTriangle, Save, Info, X, Activity, LayoutGrid, List,
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
import { categoryBadgeColor, integrationBadgeColor, categoryLabel } from '@core/lib/ui'

import type { DoctorResponse, DoctorSource, SourceChannelConfig } from '@core/types'
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

function integrationBorderClass(src: DoctorSource): string {
  if (!src.enabled) return styles.borderDisabled
  switch (src.integration_type) {
    case 'open_api': return styles.tierBorder0
    case 'official_api': return styles.tierBorder1
    case 'scraper': return styles.tierBorder2
    case 'self_hosted': return styles.tierBorder2
    default: return styles.tierBorder2
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

function IntegrationBadge({ integration_type, t }: { integration_type: string; t: (k: string) => string }) {
  if (integration_type === 'open_api') {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge0}`}>
        <Star size={10} /> {t('sources.tierCore')}
      </span>
    )
  }
  if (integration_type === 'official_api') {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge1}`}>
        <Zap size={10} /> {t('sources.tierExtended')}
      </span>
    )
  }
  if (integration_type === 'scraper') {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge2}`}>
        <Sparkles size={10} /> {t('sources.tierExperimental')}
      </span>
    )
  }
  if (integration_type === 'self_hosted') {
    return (
      <span className={`${styles.tierBadge} ${styles.tierBadge1}`}>
        <Server size={10} /> {t('sources.tierSelfHosted')}
      </span>
    )
  }
  return (
    <span className={`${styles.tierBadge} ${styles.tierBadge2}`}>
      <Sparkles size={10} /> {t('sources.tierExperimental')}
    </span>
  )
}

function KeyRequirementBadge({ value, t }: { value: DoctorSource['key_requirement']; t: (k: string, opts?: { defaultValue?: string }) => string }) {
  if (value === 'none') {
    return <Badge color="green">{t('sources.keyNone', { defaultValue: '免配置' })}</Badge>
  }
  if (value === 'optional') {
    return <Badge color="blue">{t('sources.keyOptionalShort', { defaultValue: '可选' })}</Badge>
  }
  if (value === 'required') {
    return <Badge color="amber">{t('sources.keyRequiredShort', { defaultValue: '必须' })}</Badge>
  }
  if (value === 'self_hosted') {
    return <Badge color="indigo">{t('sources.keySelfHostedShort', { defaultValue: '自建' })}</Badge>
  }
  return <Badge color="gray">—</Badge>
}

function RiskBadge({ value, t }: { value?: DoctorSource['risk_level']; t: (k: string, opts?: { defaultValue?: string }) => string }) {
  if (value === 'high') return <Badge color="red">{t('sources.riskHigh', { defaultValue: '高风险' })}</Badge>
  if (value === 'medium') return <Badge color="amber">{t('sources.riskMedium', { defaultValue: '中风险' })}</Badge>
  return <Badge color="green">{t('sources.riskLow', { defaultValue: '低风险' })}</Badge>
}

function DistributionBadge({ value, t }: { value?: DoctorSource['distribution']; t: (k: string, opts?: { defaultValue?: string }) => string }) {
  if (value === 'plugin') return <Badge color="indigo">{t('sources.distPlugin', { defaultValue: '插件' })}</Badge>
  if (value === 'extra') return <Badge color="teal">{t('sources.distExtra', { defaultValue: '可选依赖' })}</Badge>
  return <Badge color="gray">{t('sources.distCore', { defaultValue: '内置' })}</Badge>
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
      if (config.integration_type === 'scraper') {
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
  }, [proxyMode, customProxy, httpBackend, baseUrl, clearApiKey, apiKeyMode, newApiKey, sourceName, config.integration_type, addToast, t, onSaved])

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
        {config.integration_type === 'scraper' && (
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
  const [selectedCategory, setSelectedCategory] = useState<'all' | CategoryKey>('all')
  const [viewMode, setViewMode] = useState<'sources' | 'health'>('sources')
  const [displayMode, setDisplayMode] = useState<'grid' | 'list'>('grid')
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
  const statusOrder: Record<string, number> = { ok: 0, degraded: 1, needs_key: 2, error: 3, timeout: 4 }
  for (const cat of CATEGORY_ORDER) {
    sourcesByCategory[cat] = doctor.sources
      .filter((s) => s.category === cat)
      .sort((a, b) => {
        // Enabled sources first, then by status priority, then alphabetically
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
        const diff = (statusOrder[a.status] ?? 5) - (statusOrder[b.status] ?? 5)
        return diff !== 0 ? diff : a.name.localeCompare(b.name)
      })
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

      {/* View Mode Toggle */}
      <div className={styles.viewToggle}>
        <button
          type="button"
          className={`${styles.viewToggleBtn} ${viewMode === 'sources' ? styles.viewToggleBtnActive : ''}`}
          onClick={() => setViewMode('sources')}
        >
          <Server size={16} />
          {t('sources.viewSources')}
        </button>
        <button
          type="button"
          className={`${styles.viewToggleBtn} ${viewMode === 'health' ? styles.viewToggleBtnActive : ''}`}
          onClick={() => setViewMode('health')}
        >
          <Activity size={16} />
          {t('sources.viewHealth')}
        </button>
      </div>

      {viewMode === 'sources' && (<>
      {/* Filter Tabs */}
      {(() => {
        const tabs: Array<{ key: 'all' | CategoryKey; label: string; count: number; Icon?: typeof FileText }> = [
          { key: 'all', label: t('sources.categoryAll'), count: doctor.sources.length },
          { key: 'paper', label: t('sources.categoryPaper'), count: sourcesByCategory.paper?.length ?? 0, Icon: CATEGORY_ICONS.paper },
          { key: 'patent', label: t('sources.categoryPatent'), count: sourcesByCategory.patent?.length ?? 0, Icon: CATEGORY_ICONS.patent },
          ...(['general', 'professional', 'social', 'developer', 'wiki', 'video'] as CategoryKey[]).map((cat) => ({
            key: cat,
            label: t(`sources.category${cat.charAt(0).toUpperCase() + cat.slice(1)}`),
            count: sourcesByCategory[cat]?.length ?? 0,
            Icon: CATEGORY_ICONS[cat],
          })),
        ]
        return (
          <div className={styles.filterRow}>
            <div className={styles.filterTabs} role="tablist" aria-label={t('sources.pageTitle')}>
              {tabs.map((tab) => {
                const Icon = tab.Icon
                const active = selectedCategory === tab.key
                return (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    className={`${styles.filterTab} ${active ? styles.filterTabActive : ''}`}
                    onClick={() => setSelectedCategory(tab.key)}
                  >
                    {Icon && <Icon size={14} />}
                    <span>{tab.label}</span>
                    <span className={`${styles.filterTabCount} ${active ? styles.filterTabCountActive : ''}`}>{tab.count}</span>
                  </button>
                )
              })}
            </div>
            <div className={styles.displayToggle}>
              <button
                type="button"
                className={`${styles.displayToggleBtn} ${displayMode === 'grid' ? styles.displayToggleBtnActive : ''}`}
                onClick={() => setDisplayMode('grid')}
                aria-label="Grid view"
                title="Grid view"
              >
                <LayoutGrid size={16} />
              </button>
              <button
                type="button"
                className={`${styles.displayToggleBtn} ${displayMode === 'list' ? styles.displayToggleBtnActive : ''}`}
                onClick={() => setDisplayMode('list')}
                aria-label="List view"
                title="List view"
              >
                <List size={16} />
              </button>
            </div>
          </div>
        )
      })()}

      {/* Filtered Source Grid */}
      {(() => {
        const list =
          selectedCategory === 'all'
            ? CATEGORY_ORDER.flatMap((cat) => sourcesByCategory[cat] ?? [])
            : sourcesByCategory[selectedCategory] ?? []
        if (list.length === 0) return null
        if (displayMode === 'list') {
          return (
            <div className={styles.listTableWrap}>
              <table className={styles.listTable}>
                <thead>
                  <tr>
                    <th></th>
                    <th>{t('sources.colName', { defaultValue: '名称' })}</th>
                    <th>{t('sources.colDescription', { defaultValue: '描述' })}</th>
                    <th>{t('sources.colType', { defaultValue: '类型' })}</th>
                    <th>{t('sources.colKeyReq', { defaultValue: '密钥需求' })}</th>
                    <th>{t('sources.colRisk', { defaultValue: '风险' })}</th>
                    <th>{t('sources.colDistribution', { defaultValue: '分发' })}</th>
                    <th>{t('sources.colKey', { defaultValue: '密钥' })}</th>
                    <th>{t('sources.colStatus', { defaultValue: '状态' })}</th>
                    <th>{t('sources.colEnabled', { defaultValue: '启用' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((src) => (
                    <tr key={src.name} className={!src.enabled ? styles.listRowDisabled : ''}>
                      <td>
                        <StatusDot status={src.enabled ? src.status : 'disabled'} />
                      </td>
                      <td className={styles.listName}>{src.name}</td>
                      <td className={styles.listDesc}>{src.description || '—'}</td>
                      <td>
                        <IntegrationBadge integration_type={src.integration_type} t={t} />
                      </td>
                      <td>
                        <KeyRequirementBadge value={src.key_requirement} t={t} />
                      </td>
                      <td>
                        <RiskBadge value={src.risk_level} t={t} />
                      </td>
                      <td>
                        <DistributionBadge value={src.distribution} t={t} />
                      </td>
                      <td>
                        <code className={styles.listCode}>
                          {(src.credential_fields && src.credential_fields.length > 0)
                            ? src.credential_fields.join(', ')
                            : src.required_key ?? '—'}
                        </code>
                      </td>
                      <td className={styles.listMessage}>{src.message}</td>
                      <td>
                        <button
                          className={`${styles.toggleBtn} ${src.enabled ? styles.toggleBtnEnabled : ''}`}
                          onClick={() => handleToggle(src)}
                          disabled={toggling === src.name}
                          title={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                          aria-label={src.enabled ? t('sources.clickToDisable') : t('sources.clickToEnable')}
                        >
                          <span className={`${styles.toggleKnob} ${src.enabled ? styles.toggleKnobEnabled : ''}`}>
                            {src.enabled && <Check size={12} strokeWidth={3} />}
                          </span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        return (
          <m.div
            key={selectedCategory}
            className={styles.cardGrid}
            variants={staggerContainerFast}
            initial="initial"
            animate="animate"
          >
            {list.map((src) => (
              <m.div
                key={src.name}
                variants={staggerItemSmall}
                className={`${styles.sourceCard} ${!src.enabled ? styles.sourceCardDisabled : ''} ${integrationBorderClass(src)} ${expandedSource === src.name ? styles.sourceCardExpanded : ''}`}
              >
                <div className={styles.sourceCardTop} onClick={() => handleCardClick(src.name)}>
                  <StatusDot status={src.enabled ? src.status : 'disabled'} />

                  <div className={styles.cardBody}>
                    <div className={styles.sourceName}>{src.name}</div>
                    {src.description && (
                      <div className={styles.sourceDescription}>{src.description}</div>
                    )}
                    <div className={styles.badges}>
                      <IntegrationBadge integration_type={src.integration_type} t={t} />
                      <RiskBadge value={src.risk_level} t={t} />
                      <DistributionBadge value={src.distribution} t={t} />
                      {src.key_requirement === 'none' && (
                        <span className={styles.configBadgeOk}>
                          <Check size={10} />
                          {t('sources.keyNone', { defaultValue: '免配置' })}
                        </span>
                      )}
                      {src.key_requirement === 'optional' && (
                        <span className={styles.configBadgeOptional}>
                          <Key size={10} />
                          {t('sources.keyOptional', { defaultValue: '可选Key' })}
                        </span>
                      )}
                      {src.key_requirement === 'required' && (
                        <span className={styles.configBadgeKey}>
                          <Key size={10} />
                          {t('sources.keyRequired', { defaultValue: '需要Key' })}
                        </span>
                      )}
                      {src.key_requirement === 'self_hosted' && (
                        <span className={styles.configBadgeSelfHosted}>
                          <Server size={10} />
                          {t('sources.keySelfHosted', { defaultValue: '需自建' })}
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
        )
      })()}
      </>)}

      {viewMode === 'health' && (
        <>
          {/* Source Matrix */}
          <div className={styles.matrixCard}>
            <div className={styles.matrixHeader}>
              <div>
                <h3 className={styles.matrixTitle}>
                  <span className={styles.matrixCount}>{doctor.sources.length}</span>
                  {t('sources.sourceMatrix')}
                </h3>
                <p className={styles.matrixSubtitle}>{t('sources.sourceMatrixDesc')}</p>
              </div>
              <span className={styles.matrixToggle}>MATRIX VIEW</span>
            </div>
            <div className={styles.matrixGroups}>
              {CATEGORY_ORDER
                .map((cat) => ({ cat, items: sourcesByCategory[cat] ?? [] }))
                .filter((g) => g.items.length > 0)
                .map((group, idx) => (
                  <div
                    key={group.cat}
                    className={`${styles.matrixGroup} ${idx > 0 ? styles.matrixGroupDivided : ''}`}
                  >
                    <div className={styles.matrixGroupLabel}>
                      <span className={styles.matrixGroupName}>{categoryLabel(t, group.cat)}</span>
                      <span className={styles.matrixGroupCount}>{group.items.length}</span>
                    </div>
                    <div className={styles.matrixChips}>
                      {group.items.map((src) => (
                        <span key={src.name} className={styles.matrixChip} title={src.message}>
                          <span className={`${styles.matrixDot} ${
                            src.status === 'ok' ? styles.matrixDotOk
                            : (src.status === 'error' || src.status === 'timeout') ? styles.matrixDotErr
                            : styles.matrixDotWarn
                          }`} />
                          <span className={styles.matrixChipName}>{src.name}</span>
                          <span className={`${styles.matrixTier} ${
                            src.integration_type === 'open_api' ? styles.matrixTierT0
                            : (src.integration_type === 'official_api' || src.integration_type === 'self_hosted') ? styles.matrixTierT1
                            : styles.matrixTierT2
                          }`}>
                            {src.integration_type === 'open_api' ? '开放'
                             : src.integration_type === 'scraper' ? '爬虫'
                             : src.integration_type === 'official_api' ? '授权' : '自建'}
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Health Detail Table */}
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>{t('sources.healthTitle')}</h3>
            <p className={styles.sectionDesc}>{t('sources.healthDesc')}</p>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t('sources.colStatus')}</th>
                  <th>{t('sources.colSource')}</th>
                  <th>{t('sources.colCategory')}</th>
                  <th>{t('sources.colIntegration')}</th>
                  <th>{t('sources.colKeyReq', { defaultValue: '密钥需求' })}</th>
                  <th>{t('sources.colKey')}</th>
                  <th>{t('sources.colMessage')}</th>
                </tr>
              </thead>
              <tbody>
                {CATEGORY_ORDER.flatMap((cat) => sourcesByCategory[cat] ?? []).map((src) => (
                  <tr key={src.name}>
                    <td>
                      <span className={`${styles.dot} ${
                        src.status === 'ok' ? styles.dotOk
                        : (src.status === 'error' || src.status === 'timeout') ? styles.dotErr
                        : styles.dotWarn
                      }`} />
                    </td>
                    <td className={styles.tableSourceName}>{src.name}</td>
                    <td>
                      <Badge color={categoryBadgeColor(src.category)}>
                        {categoryLabel(t, src.category)}
                      </Badge>
                    </td>
                    <td>
                      <Badge color={integrationBadgeColor(src.integration_type)}>
                        {src.integration_type === 'open_api' ? '公开'
                         : src.integration_type === 'scraper' ? '爬虫'
                         : src.integration_type === 'official_api' ? '授权' : '自建'}
                      </Badge>
                    </td>
                    <td>
                      <KeyRequirementBadge value={src.key_requirement} t={t} />
                    </td>
                    <td><code className={styles.codeCell}>{src.required_key ?? '—'}</code></td>
                    <td className={styles.messageCell}>{src.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

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
