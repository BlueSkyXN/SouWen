import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Info, RefreshCw, Shield, ShieldOff, Loader2, Plug } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Card } from '../components/common/Card'
import { TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '../lib/errors'
import type { ConfigResponse, WarpStatus, HttpBackendResponse } from '../types'
import styles from './ConfigPage.module.scss'

const SCRAPER_ENGINES = [
  'duckduckgo', 'yahoo', 'brave', 'google', 'bing',
  'startpage', 'baidu', 'mojeek', 'yandex', 'google_patents',
]

const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

function HttpBackendCard() {
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

  if (loading || !data) return null

  return (
    <Card className={styles.warpCard}>
      <div className={styles.warpHeader}>
        <div className={styles.warpTitle}>
          <Plug size={18} />
          {t('httpBackend.title')}
        </div>
        <span className={`${styles.warpBadge} ${data.curl_cffi_available ? styles.enabled : styles.error}`}>
          {data.curl_cffi_available ? t('httpBackend.curlAvailable') : t('httpBackend.curlNotInstalled')}
        </span>
      </div>

      <div className={styles.infoNote} style={{ marginBottom: 12 }}>
        <Info size={14} />
        <span>{t('httpBackend.subtitle')}</span>
      </div>

      <table className={styles.table} style={{ marginBottom: 8 }}>
        <thead>
          <tr>
            <th>{t('httpBackend.source')}</th>
            <th>{t('httpBackend.backend')}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className={styles.configKey}><strong>{t('httpBackend.globalDefault')}</strong></td>
            <td>
              <select
                value={data.default}
                onChange={(e) => void handleUpdate({ default: e.target.value })}
                disabled={updating === 'default'}
              >
                {BACKEND_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>{t(`httpBackend.${opt}`)}</option>
                ))}
              </select>
            </td>
          </tr>
          {SCRAPER_ENGINES.map((engine) => {
            const override = data.overrides[engine]
            return (
              <tr key={engine}>
                <td className={styles.configKey}>{engine}</td>
                <td>
                  <select
                    value={override || 'auto'}
                    onChange={(e) => {
                      const val = e.target.value
                      void handleUpdate({ source: engine, backend: val })
                    }}
                    disabled={updating === engine}
                  >
                    <option value="auto">
                      {t('httpBackend.auto')} ({t('httpBackend.default')})
                    </option>
                    <option value="curl_cffi">{t('httpBackend.curl_cffi')}</option>
                    <option value="httpx">{t('httpBackend.httpx')}</option>
                  </select>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className={styles.infoNote}>
        <Info size={14} />
        <span>{t('httpBackend.runtimeNote')}</span>
      </div>
    </Card>
  )
}

function WarpCard() {
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
      // silently ignore — WARP API may not be available outside Docker
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

  if (loading) return null
  if (!warp) return null

  const isActive = warp.status === 'enabled' || warp.status === 'starting'
  const statusClass = styles[warp.status] || styles.disabled

  const ownerLabel = warp.owner === 'shell' ? t('warp.ownerShell')
    : warp.owner === 'python' ? t('warp.ownerPython')
    : t('warp.ownerNone')

  return (
    <Card className={styles.warpCard}>
      <div className={styles.warpHeader}>
        <div className={styles.warpTitle}>
          <Shield size={18} />
          {t('warp.title')}
        </div>
        <span className={`${styles.warpBadge} ${statusClass}`}>
          {t(`warp.${warp.status}`)}
        </span>
      </div>

      {warp.status !== 'disabled' && (
        <div className={styles.warpGrid}>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>{t('warp.mode')}</div>
            <div className={styles.fieldValue}>{warp.mode}</div>
          </div>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>{t('warp.owner')}</div>
            <div className={styles.fieldValue}>{ownerLabel}</div>
          </div>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>{t('warp.socksPort')}</div>
            <div className={styles.fieldValue}>{warp.socks_port}</div>
          </div>
          {warp.ip && (
            <div className={styles.warpField}>
              <div className={styles.fieldLabel}>{t('warp.ip')}</div>
              <div className={styles.fieldValue}>{warp.ip}</div>
            </div>
          )}
          {warp.pid > 0 && (
            <div className={styles.warpField}>
              <div className={styles.fieldLabel}>{t('warp.pid')}</div>
              <div className={styles.fieldValue}>{warp.pid}</div>
            </div>
          )}
          {warp.interface && (
            <div className={styles.warpField}>
              <div className={styles.fieldLabel}>{t('warp.interface')}</div>
              <div className={styles.fieldValue}>{warp.interface}</div>
            </div>
          )}
        </div>
      )}

      {warp.last_error && (
        <div className={styles.warpError}>{warp.last_error}</div>
      )}

      <div className={styles.warpGrid}>
        <div className={styles.warpField}>
          <div className={styles.fieldLabel}>{t('warp.availableModes')}</div>
          <div className={styles.fieldValue}>
            {warp.available_modes.wireproxy && 'wireproxy '}
            {warp.available_modes.kernel && 'kernel '}
            {!warp.available_modes.wireproxy && !warp.available_modes.kernel && '—'}
          </div>
        </div>
      </div>

      <div className={styles.warpActions}>
        {!isActive ? (
          <>
            <div className={styles.fieldGroup}>
              <label>{t('warp.mode')}</label>
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="auto">{t('warp.auto')}</option>
                {warp.available_modes.wireproxy && <option value="wireproxy">{t('warp.wireproxy')}</option>}
                {warp.available_modes.kernel && <option value="kernel">{t('warp.kernel')}</option>}
              </select>
            </div>
            <div className={styles.fieldGroup}>
              <label>{t('warp.socksPort')}</label>
              <input type="number" value={port} onChange={(e) => setPort(e.target.value)} min={1} max={65535} />
            </div>
            <div className={styles.fieldGroup}>
              <label>{t('warp.endpoint')}</label>
              <input type="text" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={t('warp.endpointPlaceholder')} />
            </div>
            <button className="btn btn-primary btn-sm" onClick={handleEnable} disabled={acting}>
              {acting ? <Loader2 size={14} className="spin" /> : <Shield size={14} />}
              {acting ? t('warp.enabling') : t('warp.enable')}
            </button>
          </>
        ) : (
          <button className="btn btn-danger btn-sm" onClick={handleDisable} disabled={acting}>
            {acting ? <Loader2 size={14} className="spin" /> : <ShieldOff size={14} />}
            {acting ? t('warp.disabling') : t('warp.disable')}
          </button>
        )}
      </div>
    </Card>
  )
}

export function ConfigPage() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloading, setReloading] = useState(false)
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchConfig = useCallback(async () => {
    setLoading(true)
    try {
      const c = await api.getConfig()
      setConfig(c)
    } catch (err) {
      addToast('error', t('config.fetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  const handleReload = useCallback(async () => {
    setReloading(true)
    try {
      const res = await api.reloadConfig()
      let msg = t('config.reloadSuccess')
      if (res.password_set) msg += ` ${t('config.passwordSet')}`
      addToast('success', msg)
      void fetchConfig()
    } catch (err) {
      addToast('error', t('config.reloadFailed', { message: formatError(err) }))
    } finally {
      setReloading(false)
    }
  }, [addToast, fetchConfig, t])

  useEffect(() => {
    void fetchConfig()
  }, [fetchConfig])

  if (loading) return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <span className="srOnly">{t('common.loading', 'Loading configuration')}</span>
      <TableSkeleton rows={10} cols={2} />
    </div>
  )

  const entries = config ? Object.entries(config) : []

  return (
    <m.div
      className={styles.page}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className={styles.actions}>
        <button
          className="btn btn-primary btn-sm"
          onClick={handleReload}
          disabled={reloading}
        >
          <RefreshCw size={14} />
          {reloading ? t('config.reloading') : t('config.reload')}
        </button>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div className={styles.infoNote}>
          <Info size={18} />
          <span>{t('config.note')}</span>
        </div>
      </Card>

      <WarpCard />

      <HttpBackendCard />

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t('config.key')}</th>
              <th>{t('config.value')}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <td className={styles.configKey}>{key}</td>
                <td className={styles.configValue}>
                  {value === '***' ? (
                    <span className={styles.masked}>{t('config.masked')}</span>
                  ) : value === null || value === undefined ? (
                    <span className={styles.nullVal}>null</span>
                  ) : typeof value === 'object' ? (
                    <code>{JSON.stringify(value)}</code>
                  ) : (
                    <span>{String(value)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </m.div>
  )
}
