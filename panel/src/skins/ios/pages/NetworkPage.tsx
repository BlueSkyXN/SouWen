/**
 * 文件用途：iOS 皮肤的网络配置页面，管理 WARP 代理、爬虫引擎等网络设置
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

// ── WARP Section ──
function WarpSection() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [warp, setWarp] = useState<WarpStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [mode, setMode] = useState('auto')
  const [port, setPort] = useState('1080')
  const [endpoint, setEndpoint] = useState('')

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
                <option value="auto">{t('warp.auto')}</option>
                {warp.available_modes.wireproxy && (
                  <option value="wireproxy">{t('warp.wireproxy')}</option>
                )}
                {warp.available_modes.kernel && (
                  <option value="kernel">{t('warp.kernel')}</option>
                )}
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
      <m.div variants={staggerItem}>
        <h1 className={styles.pageTitle}>{t('network.title', '网络与代理')}</h1>
      </m.div>

      <m.div variants={staggerItem}>
        <WarpSection />
      </m.div>

      <m.div variants={staggerItem}>
        <HttpBackendSection />
      </m.div>
    </m.div>
  )
}
