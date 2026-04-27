/**
 * 文件用途：iOS 皮肤的网络配置页面，管理 WARP 代理、爬虫引擎等网络设置
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
import { Shield, ShieldOff, AlertTriangle, Info } from 'lucide-react'
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

const WARP_MODE_OPTIONS = [
  { value: 'auto', label: '自动选择', description: '自动选择最佳可用模式' },
  { value: 'wireproxy', label: 'WireProxy (用户态)', description: '用户态 SOCKS5 代理，兼容性较好' },
  { value: 'kernel', label: '内核 WireGuard', description: '内核 WireGuard 接口，性能较高' },
  { value: 'usque', label: 'MASQUE/QUIC (usque)', description: '基于 MASQUE/QUIC 的新协议模式' },
  { value: 'warp-cli', label: '官方客户端 (warp-cli)', description: '使用 Cloudflare 官方客户端接管连接' },
  { value: 'external', label: '外部代理', description: '使用已配置的外部 WARP 代理' },
] as const

type WarpModeValue = typeof WARP_MODE_OPTIONS[number]['value']
type ConcreteWarpModeValue = Exclude<WarpModeValue, 'auto'>

function isWarpModeAvailable(warp: WarpStatus, mode: WarpModeValue) {
  if (mode === 'auto') return true
  return Boolean(warp.available_modes?.[mode as ConcreteWarpModeValue])
}

function formatAvailableWarpModes(warp: WarpStatus) {
  const modes = WARP_MODE_OPTIONS
    .filter((option) => option.value !== 'auto' && isWarpModeAvailable(warp, option.value))
    .map((option) => option.label)
  return modes.length > 0 ? modes.join('、') : '—'
}

// ── WARP Section ──
// WARP 代理配置子组件
function WarpSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [warp, setWarp] = useState<WarpStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [mode, setMode] = useState('auto')
  const [port, setPort] = useState('1080')
  const [endpoint, setEndpoint] = useState('')

  // 获取 WARP 当前状态
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

  // 启用 WARP 代理，校验端口范围并发送配置到服务器
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

  // 禁用 WARP 代理
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
      <div className={styles.formGroup}>
        <div className={styles.groupTitle}>WARP PROXY</div>
        <div className={styles.groupCard}>
          <div className={styles.formRow}>
            <span className={styles.rowLabel}>{t('network.status', 'Status')}</span>
            <span className={styles.rowValueMuted}>{t('warp.notAvailable')}</span>
          </div>
        </div>
      </div>
    )
  }

  const isActive = warp.status === 'enabled' || warp.status === 'starting'
  const statusClass = warp.status === 'enabled' ? styles.statusOn
    : warp.status === 'error' ? styles.statusErr
    : warp.status === 'starting' || warp.status === 'stopping' ? styles.statusWarn
    : styles.statusOff

  return (
    <div className={styles.formGroup}>
      <div className={styles.groupTitle}>WARP PROXY</div>
      <div className={styles.groupCard}>
        {/* Status rows */}
        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>{t('network.status', 'Status')}</span>
          <span className={`${styles.rowValue} ${statusClass}`}>
            <span className={styles.statusDot} />
            {t(`warp.${warp.status}`)}
          </span>
        </div>

        {warp.status !== 'disabled' && (
          <>
            <div className={`${styles.formRow} ${styles.formRowSep}`}>
              <span className={styles.rowLabel}>{t('network.mode', 'Mode')}</span>
              <span className={styles.rowValueMuted}>{warp.mode}</span>
            </div>
            <div className={`${styles.formRow} ${styles.formRowSep}`}>
              <span className={styles.rowLabel}>{t('network.port', 'Port')}</span>
              <span className={styles.rowValueMuted}>{warp.socks_port}</span>
            </div>
            {warp.protocol && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>协议</span>
                <span className={styles.rowValueMuted}>{warp.protocol}</span>
              </div>
            )}
            {warp.proxy_type && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>代理类型</span>
                <span className={styles.rowValueMuted}>{warp.proxy_type}</span>
              </div>
            )}
            {warp.http_port > 0 && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>HTTP 端口</span>
                <span className={styles.rowValueMuted}>{warp.http_port}</span>
              </div>
            )}
            {warp.ip && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>{t('network.ip', 'IP')}</span>
                <span className={styles.rowValueMuted}>{warp.ip}</span>
              </div>
            )}
            {warp.pid > 0 && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>{t('network.pid', 'PID')}</span>
                <span className={styles.rowValueMuted}>{warp.pid}</span>
              </div>
            )}
            {warp.interface && (
              <div className={`${styles.formRow} ${styles.formRowSep}`}>
                <span className={styles.rowLabel}>{t('network.interface', 'Interface')}</span>
                <span className={styles.rowValueMuted}>{warp.interface}</span>
              </div>
            )}
          </>
        )}
        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>可用模式</span>
          <span className={styles.rowValueMuted}>{formatAvailableWarpModes(warp)}</span>
        </div>

        {warp.last_error && (
          <div className={styles.errorBanner}>
            <AlertTriangle size={12} />
            {warp.last_error}
          </div>
        )}

        {/* Controls */}
        {!isActive ? (
          <>
            <div className={`${styles.formRow} ${styles.formRowSep}`}>
              <span className={styles.rowLabel}>{t('network.mode', 'Mode')}</span>
              <select
                className={styles.formSelect}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                {WARP_MODE_OPTIONS.map((option) => {
                  const available = isWarpModeAvailable(warp, option.value)
                  return (
                    <option key={option.value} value={option.value} disabled={!available}>
                      {option.label} — {option.description}{available ? '' : '（不可用）'}
                    </option>
                  )
                })}
              </select>
            </div>
            <div className={`${styles.formRow} ${styles.formRowSep}`}>
              <span className={styles.rowLabel}>{t('network.port', 'Port')}</span>
              <input
                className={styles.formInput}
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                min={1}
                max={65535}
              />
            </div>
            <div className={`${styles.formRow} ${styles.formRowSep}`}>
              <span className={styles.rowLabel}>{t('network.endpoint', 'Endpoint')}</span>
              <input
                className={styles.formInput}
                type="text"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                placeholder={t('warp.endpointPlaceholder')}
              />
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
// HTTP 后端配置子组件
function HttpBackendSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [data, setData] = useState<HttpBackendResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  // 获取 HTTP 后端配置
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

  // 更新 HTTP 后端配置
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
    <div className={styles.formGroup}>
      <div className={styles.groupTitle}>{t('network.httpBackend', 'HTTP BACKEND')}</div>
      <div className={styles.groupCard}>
        {/* curl_cffi status */}
        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>curl_cffi</span>
          <span className={data.curl_cffi_available ? styles.statusOn : styles.statusWarn} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 15 }}>
            <span className={styles.statusDot} />
            {data.curl_cffi_available ? t('network.curlAvailable', 'Available') : t('network.curlUnavailable', 'Unavailable')}
          </span>
        </div>

        {/* Global default */}
        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>{t('network.globalDefault', 'Default')}</span>
          <select
            className={styles.formSelect}
            value={data.default}
            onChange={(e) => void handleUpdate({ default: e.target.value })}
            disabled={updating === 'default'}
          >
            {BACKEND_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{t(`httpBackend.${opt}`)}</option>
            ))}
          </select>
        </div>

        {/* Per-engine overrides */}
        {SCRAPER_ENGINES.map((engine, i) => {
          const override = data.overrides[engine]
          return (
            <div key={engine} className={`${styles.formRow} ${i < SCRAPER_ENGINES.length - 1 ? styles.formRowSep : ''}`}>
              <span className={styles.rowLabel} style={{ fontSize: 15 }}>{engine}</span>
              <select
                className={styles.formSelect}
                value={override || 'auto'}
                onChange={(e) => void handleUpdate({ source: engine, backend: e.target.value })}
                disabled={updating === engine}
              >
                <option value="auto">{t('httpBackend.auto')}</option>
                <option value="curl_cffi">{t('httpBackend.curl_cffi')}</option>
                <option value="httpx">{t('httpBackend.httpx')}</option>
              </select>
            </div>
          )
        })}
      </div>

      <div className={styles.groupFootnote}>
        <Info size={11} />
        <span>{t('httpBackend.runtimeNote')}</span>
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
    <div className={styles.formGroup}>
      <div className={styles.groupTitle}>{t('proxy.title')}</div>
      <div className={styles.groupCard}>
        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>{t('proxy.socksSupported')}</span>
          <span
            className={socksSupported ? styles.statusOn : styles.statusWarn}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 15 }}
          >
            <span className={styles.statusDot} />
            {socksSupported ? t('proxy.socksAvailable') : t('proxy.socksUnavailable')}
          </span>
        </div>

        <div className={`${styles.formRow} ${styles.formRowSep}`}>
          <span className={styles.rowLabel}>{t('proxy.globalProxy')}</span>
          <input
            className={styles.formInput}
            type="text"
            value={proxy}
            onChange={(e) => setProxy(e.target.value)}
            placeholder={t('proxy.globalProxyPlaceholder')}
          />
        </div>

        <div className={`${styles.formRow} ${styles.formRowSep}`} style={{ alignItems: 'flex-start' }}>
          <span className={styles.rowLabel}>{t('proxy.proxyPool')}</span>
          <textarea
            className={styles.formInput}
            value={poolText}
            onChange={(e) => setPoolText(e.target.value)}
            placeholder={t('proxy.proxyPoolPlaceholder')}
            rows={3}
            style={{ fontFamily: 'monospace', resize: 'vertical', minHeight: '4rem' }}
          />
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
      <div className={styles.groupFootnote}>
        <Info size={11} />
        <span>{t('proxy.description')}</span>
      </div>
    </div>
  )
}

// ── Main NetworkPage ──
// 网络配置页面主组件
export function NetworkPage() {
  const { t } = useTranslation()

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <m.div variants={staggerItem}>
        <h1 className={styles.pageTitle}>{t('network.title', '网络与代理')}</h1>
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
