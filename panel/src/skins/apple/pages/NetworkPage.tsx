/**
 * 文件用途：Apple 皮肤的网络配置页面，管理 WARP 代理、爬虫引擎、HTTP 后端等网络设置
 *
 * 组件/函数清单：
 *   NetworkPage（函数组件）
 *     - 功能：提供网络配置的主入口，包含 WARP、爬虫引擎、HTTP 后端三个子区域
 *
 *   WarpSection（子组件）
 *     - 功能：WARP 代理的启用/禁用和配置（模式、端口、端点）
 *     - State 状态：warp (WarpStatus) WARP 状态, mode 代理模式, port 监听端口, endpoint 自定义端点
 *     - 关键钩子：getWarpStatus 获取状态, enableWarp 启用代理, disableWarp 禁用代理
 *
 *   ScraperEngineSection（子组件）
 *     - 功能：配置默认爬虫引擎，支持多个搜索引擎（Google、Bing 等）
 *
 *   HttpBackendSection（子组件）
 *     - 功能：选择 HTTP 请求后端（auto/curl_cffi/httpx）
 *
 * 模块依赖：
 *   - react: 状态管理
 *   - react-i18next: 国际化翻译
 *   - framer-motion: 动画
 *   - lucide-react: 图标
 *   - @core/services/api: 网络配置 API
 *   - @core/stores/notificationStore: 提示消息
 *   - NetworkPage.module.scss: 样式
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Wifi, Shield, ShieldOff, Plug, Activity, AlertTriangle, Info } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { WarpStatus, HttpBackendResponse } from '@core/types'
import styles from './NetworkPage.module.scss'

const SCRAPER_ENGINES = [
  'duckduckgo', 'yahoo', 'brave', 'google', 'bing',
  'startpage', 'baidu', 'mojeek', 'yandex', 'google_patents',
]

const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

// ── WARP Section ──
/**
 * WarpSection 子组件 - WARP 代理配置
 * 显示 WARP 状态（启用/禁用），支持配置模式、端口和端点
 */
function WarpSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [warp, setWarp] = useState<WarpStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [mode, setMode] = useState('auto')
  const [port, setPort] = useState('1080')
  const [endpoint, setEndpoint] = useState('')

  /**
   * 获取 WARP 当前状态
   */
  const fetchWarp = useCallback(async () => {
    try {
      const s = await api.getWarpStatus()
      setWarp(s)
    } catch {
      setWarp(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void fetchWarp() }, [fetchWarp])

  /**
   * 启用 WARP 代理
   * 校验端口范围（1-65535），发送配置到服务器
   */
  const handleEnable = useCallback(async () => {
    setActing(true)
    try {
      const portNum = Math.min(Math.max(parseInt(port) || 1080, 1), 65535)
      const res = await api.enableWarp(mode, portNum, endpoint || undefined)
      addToast('success', t('warp.enableSuccess', { mode: res.mode, ip: res.ip }))
      void fetchWarp()
    } catch (err) {
      addToast('error', t('warp.enableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [mode, port, endpoint, addToast, fetchWarp, t])

  /**
   * 禁用 WARP 代理
   */
  const handleDisable = useCallback(async () => {
    setActing(true)
    try {
      await api.disableWarp()
      addToast('success', t('warp.disableSuccess'))
      void fetchWarp()
    } catch (err) {
      addToast('error', t('warp.disableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [addToast, fetchWarp, t])

  if (loading) return <Spinner label={t('common.loading', 'Loading...')} />

  if (!warp) {
    return (
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <Shield size={14} />
          {t('network.warpProxy', 'WARP Proxy')}
        </div>
        <div className={styles.sectionBody}>
          <div className={styles.infoNote}>
            <Info size={12} />
            <span>{t('warp.notAvailable')}</span>
          </div>
        </div>
      </div>
    )
  }

  const isActive = warp.status === 'enabled' || warp.status === 'starting'
  const statusClass = warp.status === 'enabled' ? styles.statusOn
    : warp.status === 'error' ? styles.statusError
    : warp.status === 'starting' || warp.status === 'stopping' ? styles.statusWarn
    : styles.statusOff

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <Shield size={14} />
        {t('network.warpProxy', 'WARP Proxy')}
      </div>
      <div className={styles.sectionBody}>
        {/* Status display */}
        <div className={styles.statusGrid}>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>{t('network.status', 'Status')}</span>
            <span className={`${styles.statusValue} ${statusClass}`}>
              <span className={styles.statusDot} />
              {t(`warp.${warp.status}`)}
            </span>
          </div>
          {warp.status !== 'disabled' && (
            <>
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>{t('network.mode', 'Mode')}</span>
                <span className={styles.statusValue}>{warp.mode}</span>
              </div>
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>{t('network.port', 'Port')}</span>
                <span className={styles.statusValue}>{warp.socks_port}</span>
              </div>
              {warp.ip && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>{t('network.ip', 'IP')}</span>
                  <span className={styles.statusValue}>{warp.ip}</span>
                </div>
              )}
              {warp.pid > 0 && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>{t('network.pid', 'PID')}</span>
                  <span className={styles.statusValue}>{warp.pid}</span>
                </div>
              )}
              {warp.interface && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>{t('network.interface', 'Interface')}</span>
                  <span className={styles.statusValue}>{warp.interface}</span>
                </div>
              )}
            </>
          )}
        </div>

        {warp.last_error && (
          <div className={styles.errorBanner}>
            <AlertTriangle size={12} />
            {warp.last_error}
          </div>
        )}

        <div className={styles.divider} />

        {/* Controls */}
        {!isActive ? (
          <>
            <div className={styles.formGrid}>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>{t('network.mode', 'Mode')}</label>
                <select
                  className={styles.formSelect}
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="auto">{t('warp.auto')}</option>
                  {warp.available_modes.wireproxy && (
                    <option value="wireproxy">{t('warp.wireproxy')}</option>
                  )}
                  {warp.available_modes.kernel && (
                    <option value="kernel">{t('warp.kernel')}</option>
                  )}
                </select>
              </div>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>{t('network.port', 'Port')}</label>
                <input
                  className={styles.formInput}
                  type="number"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  min={1}
                  max={65535}
                />
              </div>
              <div className={styles.formRow}>
                <label className={styles.formLabel}>{t('network.endpoint', 'Endpoint')}</label>
                <input
                  className={styles.formInput}
                  type="text"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder={t('warp.endpointPlaceholder')}
                />
              </div>
            </div>

            <div className={styles.actionRow}>
              <button
                className={styles.actionBtn}
                onClick={handleEnable}
                disabled={acting}
              >
                <Shield size={14} />
                {acting ? t('warp.enabling') : t('warp.enable', 'Enable')}
              </button>
            </div>
          </>
        ) : (
          <div className={styles.actionRow}>
            <button
              className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
              onClick={handleDisable}
              disabled={acting}
            >
              <ShieldOff size={14} />
              {acting ? t('warp.disabling') : t('warp.disable', 'Disable')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── HTTP Backend Section ──
function HttpBackendSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [data, setData] = useState<HttpBackendResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await api.getHttpBackend()
      setData(res)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void fetchData() }, [fetchData])

  const handleUpdate = useCallback(async (params: {
    default?: string
    source?: string
    backend?: string
  }) => {
    const key = params.source || 'default'
    setUpdating(key)
    try {
      const res = await api.updateHttpBackend(params)
      setData((prev) => prev ? {
        ...prev,
        default: res.default,
        overrides: res.overrides,
      } : prev)
      addToast('success', t('httpBackend.updateSuccess'))
    } catch (err) {
      addToast('error', t('httpBackend.updateFailed', { message: formatError(err) }))
    } finally {
      setUpdating(null)
    }
  }, [addToast, t])

  if (loading) return <Spinner label={t('common.loading', 'Loading...')} />
  if (!data) return null

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <Plug size={14} />
        {t('network.httpBackend', 'HTTP Backend')}
        <span className={`${styles.curlBadge} ${data.curl_cffi_available ? styles.curlAvail : styles.curlMissing}`}>
          {data.curl_cffi_available
            ? t('network.curlAvailable', 'curl_cffi available')
            : t('network.curlUnavailable', 'curl_cffi unavailable')}
        </span>
      </div>
      <div className={styles.sectionBody}>
        {/* Global default */}
        <div className={`${styles.engineRow} ${styles.engineRowDefault}`}>
          <span className={styles.engineName}>{t('network.globalDefault', 'Default')}</span>
          <select
            className={styles.engineSelect}
            value={data.default}
            onChange={(e) => void handleUpdate({ default: e.target.value })}
            disabled={updating === 'default'}
          >
            {BACKEND_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{t(`httpBackend.${opt}`)}</option>
            ))}
          </select>
        </div>

        <div className={styles.divider} />

        {/* Per-engine overrides */}
        {SCRAPER_ENGINES.map((engine) => {
          const override = data.overrides[engine]
          return (
            <div key={engine} className={styles.engineRow}>
              <span className={styles.engineName}>{engine}</span>
              <select
                className={styles.engineSelect}
                value={override || 'auto'}
                onChange={(e) => void handleUpdate({ source: engine, backend: e.target.value })}
                disabled={updating === engine}
              >
                <option value="auto">{t('httpBackend.auto')} ({t('httpBackend.default')})</option>
                <option value="curl_cffi">{t('httpBackend.curl_cffi')}</option>
                <option value="httpx">{t('httpBackend.httpx')}</option>
              </select>
            </div>
          )
        })}

        <div className={styles.divider} />

        <div className={styles.infoNote}>
          <Info size={12} />
          <span>{t('httpBackend.runtimeNote')}</span>
        </div>
      </div>
    </div>
  )
}

// ── Proxy Config Section ──
function ProxyConfigSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [proxy, setProxy] = useState('')
  const [poolText, setPoolText] = useState('')
  const [socksSupported, setSocksSupported] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getProxyConfig()
      setProxy(data.proxy || '')
      setPoolText((data.proxy_pool || []).join('\n'))
      setSocksSupported(data.socks_supported)
    } catch {
      addToast('error', t('proxy.fetchFailed'))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => { void fetchConfig() }, [fetchConfig])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const pool = poolText.split('\n').map((s) => s.trim()).filter(Boolean)
      await api.updateProxyConfig({ proxy: proxy.trim() || '', proxy_pool: pool })
      addToast('success', t('proxy.saved'))
    } catch (err) {
      addToast('error', t('proxy.saveFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [proxy, poolText, addToast, t])

  const handleClear = useCallback(async () => {
    setSaving(true)
    try {
      await api.updateProxyConfig({ proxy: '', proxy_pool: [] })
      setProxy('')
      setPoolText('')
      addToast('success', t('proxy.saved'))
    } catch (err) {
      addToast('error', t('proxy.saveFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [addToast, t])

  if (loading) return <Spinner label={t('common.loading', 'Loading...')} />

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <Shield size={14} />
        {t('proxy.title')}
        <span className={`${styles.curlBadge} ${socksSupported ? styles.curlAvail : styles.curlMissing}`}>
          {socksSupported ? t('proxy.socksAvailable') : t('proxy.socksUnavailable')}
        </span>
      </div>
      <div className={styles.sectionBody}>
        <div className={styles.infoNote}>
          <Info size={12} />
          <span>{t('proxy.description')}</span>
        </div>

        <div className={styles.formGrid}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>{t('proxy.globalProxy')}</label>
            <input
              className={styles.formInput}
              type="text"
              value={proxy}
              onChange={(e) => setProxy(e.target.value)}
              placeholder={t('proxy.globalProxyPlaceholder')}
            />
          </div>
          <div className={styles.formRow} style={{ alignItems: 'flex-start' }}>
            <label className={styles.formLabel}>{t('proxy.proxyPool')}</label>
            <textarea
              className={styles.formInput}
              value={poolText}
              onChange={(e) => setPoolText(e.target.value)}
              placeholder={t('proxy.proxyPoolPlaceholder')}
              rows={3}
              style={{ fontFamily: 'monospace', resize: 'vertical', minHeight: '4rem' }}
            />
          </div>
        </div>

        <div className={styles.infoNote}>
          <Info size={12} />
          <span>{t('proxy.poolDescription')}</span>
        </div>

        <div className={styles.actionRow}>
          <button
            className={styles.actionBtn}
            onClick={handleSave}
            disabled={saving}
          >
            <Shield size={14} />
            {saving ? t('proxy.saving') : t('proxy.save')}
          </button>
          <button
            className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
            onClick={handleClear}
            disabled={saving}
          >
            {t('proxy.clear')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main NetworkPage ──
export function NetworkPage() {
  const { t } = useTranslation()

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Header */}
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>
            <Wifi size={20} />
            {t('network.title', 'Network')}
          </h1>
          <p className={styles.pageDesc}>
            {t('network.pageSubtitle', 'WARP proxy and HTTP backend configuration')}
          </p>
        </div>
        <div className={styles.headerBadge}>
          <Activity size={14} />
          {t('network.active', 'Active')}
        </div>
      </m.div>

      <m.div variants={staggerItem}>
        <WarpSection />
      </m.div>

      <m.div variants={staggerItem}>
        <ProxyConfigSection />
      </m.div>

      <m.div variants={staggerItem}>
        <HttpBackendSection />
      </m.div>
    </m.div>
  )
}
