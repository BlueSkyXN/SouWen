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
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <Shield size={14} />
          [WARP_PROXY]
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
        [WARP_PROXY]
      </div>
      <div className={styles.sectionBody}>
        {/* Status display */}
        <div className={styles.statusGrid}>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>STATUS</span>
            <span className={`${styles.statusValue} ${statusClass}`}>
              <span className={styles.statusDot} />
              {t(`warp.${warp.status}`).toUpperCase()}
            </span>
          </div>
          {warp.status !== 'disabled' && (
            <>
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>MODE</span>
                <span className={styles.statusValue}>{warp.mode}</span>
              </div>
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>PORT</span>
                <span className={styles.statusValue}>{warp.socks_port}</span>
              </div>
              {warp.ip && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>IP</span>
                  <span className={styles.statusValue}>{warp.ip}</span>
                </div>
              )}
              {warp.pid > 0 && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>PID</span>
                  <span className={styles.statusValue}>{warp.pid}</span>
                </div>
              )}
              {warp.interface && (
                <div className={styles.statusRow}>
                  <span className={styles.statusLabel}>INTERFACE</span>
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
                <label className={styles.formLabel}>mode</label>
                <span className={styles.formSep}>───</span>
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
                <label className={styles.formLabel}>port</label>
                <span className={styles.formSep}>───</span>
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
                <label className={styles.formLabel}>endpoint</label>
                <span className={styles.formSep}>───</span>
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
                {acting ? t('warp.enabling') : 'ENABLE'}
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
              {acting ? t('warp.disabling') : 'DISABLE'}
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
        [HTTP_BACKEND]
        <span className={`${styles.curlBadge} ${data.curl_cffi_available ? styles.curlAvail : styles.curlMissing}`}>
          {data.curl_cffi_available ? 'CURL_CFFI: OK' : 'CURL_CFFI: N/A'}
        </span>
      </div>
      <div className={styles.sectionBody}>
        {/* Global default */}
        <div className={`${styles.engineRow} ${styles.engineRowDefault}`}>
          <span className={styles.engineName}>GLOBAL_DEFAULT</span>
          <span className={styles.engineSep}>──</span>
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
              <span className={styles.engineSep}>──</span>
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
            NETWORK.CONFIG
          </h1>
          <p className={styles.pageDesc}>
            {t('network.pageSubtitle', 'WARP 代理和 HTTP 后端配置')}
          </p>
        </div>
        <div className={styles.headerBadge}>
          <Activity size={14} />
          ACTIVE
        </div>
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
