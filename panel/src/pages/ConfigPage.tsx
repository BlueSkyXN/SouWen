import { useEffect, useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Info, RefreshCw, Shield, ShieldOff, Plug,
  Settings, Globe, Search, Wrench, HelpCircle, CheckCircle2,
  CircleDot, Wifi,
} from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Card } from '../components/common/Card'
import { Accordion } from '../components/common/Accordion'
import { Tooltip } from '../components/common/Tooltip'
import { Input } from '../components/common/Input'
import { Button } from '../components/common/Button'
import { Badge } from '../components/common/Badge'
import { TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '../lib/errors'
import { staggerContainer, staggerItem } from '../lib/animations'
import type { ConfigResponse, WarpStatus, HttpBackendResponse } from '../types'
import styles from './ConfigPage.module.scss'

const SCRAPER_ENGINES = [
  'duckduckgo', 'yahoo', 'brave', 'google', 'bing',
  'startpage', 'baidu', 'mojeek', 'yandex', 'google_patents',
]

const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

// Keys considered "basic" settings
const BASIC_KEYS = ['api_password', 'log_level', 'max_workers', 'host', 'port', 'debug']
// Keys considered "network" settings
const NETWORK_KEYS = ['proxy', 'http_backend', 'timeout', 'concurrent_limit']
// Keys considered "search" settings
const SEARCH_KEYS = ['searxng_url', 'cache_enabled', 'cache_ttl']
// Keys that are sensitive (masked)
const MASKED_KEYS = new Set(['api_password'])

interface ConfigSection {
  id: string
  titleKey: string
  descKey: string
  icon: React.ReactNode
  keys: string[]
}

const CONFIG_SECTIONS: ConfigSection[] = [
  { id: 'basic', titleKey: 'config.sectionBasic', descKey: 'config.sectionBasicDesc', icon: <Settings size={16} />, keys: BASIC_KEYS },
  { id: 'network', titleKey: 'config.sectionNetwork', descKey: 'config.sectionNetworkDesc', icon: <Globe size={16} />, keys: NETWORK_KEYS },
  { id: 'search', titleKey: 'config.sectionSearch', descKey: 'config.sectionSearchDesc', icon: <Search size={16} />, keys: SEARCH_KEYS },
]

type TFunc = ReturnType<typeof useTranslation>['t']

function getConfigLabel(key: string, t: TFunc): string {
  return t(`config.labels.${key}`, { defaultValue: key })
}

function getConfigDescription(key: string, t: TFunc): string | undefined {
  const desc = t(`config.descriptions.${key}`, { defaultValue: '' })
  return desc || undefined
}

function ConfigRow({ configKey, value, t }: { configKey: string; value: unknown; t: ReturnType<typeof useTranslation>['t'] }) {
  const label = getConfigLabel(configKey, t)
  const description = getConfigDescription(configKey, t)
  const isMasked = value === '***' || MASKED_KEYS.has(configKey)
  const isNull = value === null || value === undefined

  return (
    <div className={styles.configRow}>
      <div className={styles.configRowLabel}>
        <span className={styles.configRowName}>{label}</span>
        {description && (
          <Tooltip content={description} position="right">
            <HelpCircle size={13} className={styles.helpIcon} />
          </Tooltip>
        )}
        <span className={styles.configRowKey}>{configKey}</span>
      </div>
      <div className={styles.configRowValue}>
        {isMasked && value === '***' ? (
          <Badge color="green">
            <CheckCircle2 size={12} />
            {t('config.configured')}
          </Badge>
        ) : isNull ? (
          <span className={styles.nullVal}>{t('config.notSet')}</span>
        ) : typeof value === 'object' ? (
          <code className={styles.codeVal}>{JSON.stringify(value)}</code>
        ) : typeof value === 'boolean' ? (
          <Badge color={value ? 'green' : 'gray'}>{String(value)}</Badge>
        ) : (
          <span className={styles.plainVal}>{String(value)}</span>
        )}
      </div>
    </div>
  )
}

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
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>
          <Plug size={18} />
          {t('httpBackend.title')}
        </div>
        <Badge color={data.curl_cffi_available ? 'green' : 'red'}>
          {data.curl_cffi_available ? t('httpBackend.curlAvailable') : t('httpBackend.curlNotInstalled')}
        </Badge>
      </div>

      <div className={styles.infoNote}>
        <Info size={14} />
        <span>{t('httpBackend.subtitle')}</span>
      </div>

      <div className={styles.engineList}>
        {/* Global default row */}
        <div className={`${styles.engineRow} ${styles.engineRowDefault}`}>
          <div className={styles.engineName}>
            <strong>{t('httpBackend.globalDefault')}</strong>
            <Tooltip content={t('httpBackend.autoTip')} position="right">
              <HelpCircle size={13} className={styles.helpIcon} />
            </Tooltip>
          </div>
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

        {SCRAPER_ENGINES.map((engine) => {
          const override = data.overrides[engine]
          const engineLabel = t(`httpBackend.engineNames.${engine}`, engine)
          return (
            <div key={engine} className={styles.engineRow}>
              <div className={styles.engineName}>{engineLabel}</div>
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
      </div>

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

  // WARP not available — show info message instead of hiding
  if (!warp) return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>
          <Shield size={18} />
          {t('warp.title')}
        </div>
        <Badge color="gray">{t('warp.disabled')}</Badge>
      </div>
      <div className={styles.infoNote}>
        <Info size={14} />
        <span>{t('warp.notAvailable')}</span>
      </div>
    </Card>
  )

  const isActive = warp.status === 'enabled' || warp.status === 'starting'
  const statusColor = warp.status === 'enabled' ? 'green'
    : warp.status === 'error' ? 'red'
    : warp.status === 'starting' || warp.status === 'stopping' ? 'amber'
    : 'gray'

  const ownerLabel = warp.owner === 'shell' ? t('warp.ownerShell')
    : warp.owner === 'python' ? t('warp.ownerPython')
    : t('warp.ownerNone')

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>
          <Shield size={18} />
          {t('warp.title')}
        </div>
        <div className={styles.statusIndicator}>
          <span className={`${styles.statusDot} ${styles[`dot_${statusColor}`]}`} />
          <Badge color={statusColor}>{t(`warp.${warp.status}`)}</Badge>
        </div>
      </div>

      {warp.status !== 'disabled' && (
        <div className={styles.warpGrid}>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>
              <CircleDot size={12} />
              {t('warp.mode')}
            </div>
            <div className={styles.fieldValue}>{warp.mode}</div>
          </div>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>
              <Settings size={12} />
              {t('warp.owner')}
            </div>
            <div className={styles.fieldValue}>{ownerLabel}</div>
          </div>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>
              <Wifi size={12} />
              {t('warp.socksPort')}
            </div>
            <div className={styles.fieldValue}>{warp.socks_port}</div>
          </div>
          {warp.ip && (
            <div className={styles.warpField}>
              <div className={styles.fieldLabel}>
                <Globe size={12} />
                {t('warp.ip')}
              </div>
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

      <div className={styles.warpModes}>
        <span className={styles.fieldLabelSmall}>{t('warp.availableModes')}</span>
        <span className={styles.fieldValueInline}>
          {warp.available_modes.wireproxy && 'wireproxy '}
          {warp.available_modes.kernel && 'kernel '}
          {!warp.available_modes.wireproxy && !warp.available_modes.kernel && '—'}
        </span>
      </div>

      <div className={styles.warpActions}>
        {!isActive ? (
          <>
            <div className={styles.warpForm}>
              <div className={styles.formField}>
                <label className={styles.formLabel}>{t('warp.mode')}</label>
                <Tooltip content={t('warp.modeDesc')} position="top">
                  <HelpCircle size={13} className={styles.helpIcon} />
                </Tooltip>
                <select className={styles.formSelect} value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="auto">{t('warp.auto')}</option>
                  {warp.available_modes.wireproxy && <option value="wireproxy">{t('warp.wireproxy')}</option>}
                  {warp.available_modes.kernel && <option value="kernel">{t('warp.kernel')}</option>}
                </select>
              </div>
              <Input
                label={t('warp.socksPort')}
                description={t('warp.portDesc')}
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                min={1}
                max={65535}
              />
              <Input
                label={t('warp.endpoint')}
                description={t('warp.endpointDesc')}
                type="text"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                placeholder={t('warp.endpointPlaceholder')}
              />
            </div>
            <Button
              variant="primary"
              size="sm"
              loading={acting}
              icon={<Shield size={14} />}
              onClick={handleEnable}
            >
              {acting ? t('warp.enabling') : t('warp.enable')}
            </Button>
          </>
        ) : (
          <Button
            variant="danger"
            size="sm"
            loading={acting}
            icon={<ShieldOff size={14} />}
            onClick={handleDisable}
          >
            {acting ? t('warp.disabling') : t('warp.disable')}
          </Button>
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

  // Categorize config entries into sections
  const { sections, advancedEntries } = useMemo(() => {
    const entries = config ? Object.entries(config) : []
    const categorized = new Set<string>()

    const secs = CONFIG_SECTIONS.map((section) => {
      const items = section.keys
        .filter((key) => entries.some(([k]) => k === key))
        .map((key) => {
          categorized.add(key)
          const entry = entries.find(([k]) => k === key)!
          return { key: entry[0], value: entry[1] }
        })
      return { ...section, items }
    })

    // Everything else goes into advanced
    const advanced = entries
      .filter(([key]) => !categorized.has(key))
      .map(([key, value]) => ({ key, value }))

    return { sections: secs, advancedEntries: advanced }
  }, [config])

  if (loading) return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <span className="srOnly">{t('common.loading', 'Loading configuration')}</span>
      <TableSkeleton rows={10} cols={2} />
    </div>
  )

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* Header with reload button */}
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>{t('config.title')}</h1>
          <p className={styles.pageDesc}>{t('config.note')}</p>
        </div>
        <Button
          variant="primary"
          size="sm"
          loading={reloading}
          icon={<RefreshCw size={14} />}
          onClick={handleReload}
        >
          {reloading ? t('config.reloading') : t('config.reload')}
        </Button>
      </m.div>

      {/* Config sections with Accordion */}
      <m.div className={styles.accordionGroup} variants={staggerItem}>
        {/* Basic Settings — always visible */}
        <Accordion
          title={t('config.sectionBasic')}
          description={t('config.sectionBasicDesc')}
          icon={<Settings size={16} />}
          defaultOpen
        >
          <div className={styles.configRows}>
            {sections[0].items.map(({ key, value }) => (
              <ConfigRow key={key} configKey={key} value={value} t={t} />
            ))}
          </div>
        </Accordion>

        {/* Network Settings */}
        <Accordion
          title={t('config.sectionNetwork')}
          description={t('config.sectionNetworkDesc')}
          icon={<Globe size={16} />}
        >
          <div className={styles.configRows}>
            {sections[1].items.map(({ key, value }) => (
              <ConfigRow key={key} configKey={key} value={value} t={t} />
            ))}
          </div>
        </Accordion>

        {/* Search Engine Settings */}
        <Accordion
          title={t('config.sectionSearch')}
          description={t('config.sectionSearchDesc')}
          icon={<Search size={16} />}
        >
          <div className={styles.configRows}>
            {sections[2].items.map(({ key, value }) => (
              <ConfigRow key={key} configKey={key} value={value} t={t} />
            ))}
          </div>
        </Accordion>

        {/* Advanced Settings */}
        {advancedEntries.length > 0 && (
          <Accordion
            title={t('config.sectionAdvanced')}
            description={t('config.sectionAdvancedDesc')}
            icon={<Wrench size={16} />}
          >
            <div className={styles.configRows}>
              {advancedEntries.map(({ key, value }) => (
                <ConfigRow key={key} configKey={key} value={value} t={t} />
              ))}
            </div>
          </Accordion>
        )}
      </m.div>

      {/* HTTP Backend Card */}
      <m.div variants={staggerItem}>
        <HttpBackendCard />
      </m.div>

      {/* WARP Card */}
      <m.div variants={staggerItem}>
        <WarpCard />
      </m.div>
    </m.div>
  )
}
