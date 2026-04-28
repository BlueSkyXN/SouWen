/**
 * WARP 专属管理页面 - souwen-nebula skin
 *
 * 集中展示 Cloudflare WARP 状态、模式能力、启停配置、高级配置和运行环境信息。
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle2,
  CircleDot,
  Cloud,
  Container,
  Download,
  ExternalLink,
  Globe,
  HelpCircle,
  KeyRound,
  Loader2,
  Network,
  Package,
  RefreshCw,
  Route,
  Server,
  Settings,
  Shield,
  ShieldCheck,
  ShieldOff,
  TerminalSquare,
  Wifi,
  XCircle,
} from 'lucide-react'
import { api } from '@core/services/api'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { WarpComponentInfo, WarpConfigResponse, WarpModeInfo, WarpStatus, WarpTestResult } from '@core/types'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { Input } from '../components/common/Input'
import { Tooltip } from '../components/common/Tooltip'
import styles from './WarpPage.module.scss'

type BadgeColor = 'green' | 'blue' | 'amber' | 'red' | 'gray' | 'indigo' | 'teal'

const DEFAULT_MODES = ['auto', 'wireproxy', 'kernel', 'usque', 'warp-cli', 'external']

function statusColor(status?: WarpStatus['status']): BadgeColor {
  if (status === 'enabled') return 'green'
  if (status === 'error') return 'red'
  if (status === 'starting' || status === 'stopping') return 'amber'
  return 'gray'
}

function modeAvailable(mode: WarpModeInfo) {
  return mode.installed && (mode.id !== 'external' || Boolean(mode.configured))
}

function normalizePort(value: string, fallback: number, min = 0) {
  const n = Number.parseInt(value, 10)
  if (Number.isNaN(n)) return fallback
  return Math.min(Math.max(n, min), 65535)
}

function ownerLabel(t: ReturnType<typeof useTranslation>['t'], owner?: string) {
  if (owner === 'shell') return t('warp.ownerShell')
  if (owner === 'python') return t('warp.ownerPython')
  return t('warp.ownerNone')
}

function usqueTransportLabel(t: ReturnType<typeof useTranslation>['t'], transport?: string) {
  if (transport === 'auto') return t('warp.usqueTransportAuto')
  if (transport === 'http2') return t('warp.usqueTransportHttp2')
  return t('warp.usqueTransportQuic')
}

function WarpStatusCard({ warp, loading, refreshing, onRefresh }: {
  warp: WarpStatus | null
  loading: boolean
  refreshing: boolean
  onRefresh: () => void
}) {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<WarpTestResult | null>(null)

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await api.testWarp()
      setTestResult(result)
      addToast(result.ok ? 'success' : 'info', result.ok
        ? t('warp.testSuccess', { ip: result.ip })
        : t('warp.testFailed', { message: result.ip || 'unknown' }))
    } catch (err) {
      addToast('error', t('warp.testFailed', { message: formatError(err) }))
    } finally {
      setTesting(false)
    }
  }, [addToast, t])

  if (loading) {
    return (
      <Card className={styles.sectionCard}>
        <div className={styles.loadingState}><Loader2 size={18} /> {t('warp.loading')}</div>
      </Card>
    )
  }

  if (!warp) {
    return (
      <Card className={styles.sectionCard}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionTitle}><Shield size={18} />{t('warp.title')}</div>
          <Badge color="gray">{t('warp.disabled')}</Badge>
        </div>
        <div className={styles.infoNote}><AlertCircle size={14} />{t('warp.notAvailable')}</div>
      </Card>
    )
  }

  const color = statusColor(warp.status)
  const canTest = warp.status === 'enabled'

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><ShieldCheck size={18} />{t('warp.statusCard')}</div>
        <div className={styles.statusIndicator}>
          <span className={`${styles.statusDot} ${styles[`dot_${color}`]}`} />
          <Badge color={color}>{t(`warp.${warp.status}`)}</Badge>
        </div>
      </div>

      <div className={styles.statusPanel}>
        <StatusField icon={<CircleDot size={13} />} label={t('warp.mode')} value={warp.mode || '—'} />
        <StatusField icon={<Network size={13} />} label={t('warp.protocol')} value={warp.protocol || '—'} />
        <StatusField icon={<Route size={13} />} label={t('warp.proxyType')} value={warp.proxy_type || '—'} />
        <StatusField icon={<Globe size={13} />} label={t('warp.ip')} value={warp.ip || '—'} />
        <StatusField icon={<Wifi size={13} />} label={t('warp.socksPort')} value={String(warp.socks_port || '—')} />
        <StatusField icon={<Cloud size={13} />} label={t('warp.httpPort')} value={warp.http_port ? String(warp.http_port) : t('warp.disabledShort')} />
        <StatusField icon={<TerminalSquare size={13} />} label={t('warp.pid')} value={warp.pid > 0 ? String(warp.pid) : '—'} />
        <StatusField icon={<Settings size={13} />} label={t('warp.interface')} value={warp.interface || '—'} />
      </div>

      {testResult && (
        <div className={styles.testResult}>
          {testResult.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
          <span>{t('warp.testResult', { ip: testResult.ip, mode: testResult.mode, protocol: testResult.protocol })}</span>
        </div>
      )}

      {warp.last_error && <div className={styles.warpError}>{warp.last_error}</div>}

      <div className={styles.cardActions}>
        <Button variant="primary" size="sm" icon={<Wifi size={14} />} loading={testing} disabled={!canTest} onClick={() => void handleTest()}>
          {testing ? t('warp.testing') : t('warp.testConnection')}
        </Button>
        <Button variant="outline" size="sm" icon={<RefreshCw size={14} />} loading={refreshing} onClick={onRefresh}>
          {t('dashboard.refresh')}
        </Button>
      </div>
    </Card>
  )
}

function StatusField({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className={styles.statusField}>
      <div className={styles.fieldLabel}>{icon}{label}</div>
      <div className={styles.fieldValue}>{value}</div>
    </div>
  )
}

function WarpModesCard({ modes, activeMode }: { modes: WarpModeInfo[]; activeMode?: string }) {
  const { t } = useTranslation()
  const modeMap = useMemo(() => new Map(modes.map((mode) => [mode.id, mode])), [modes])

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><Network size={18} />{t('warp.modesCard')}</div>
        <Badge color="blue">{t('warp.modeCount', { count: modes.length })}</Badge>
      </div>
      <div className={styles.modesGrid}>
        {DEFAULT_MODES.filter((id) => id !== 'auto').map((id) => {
          const mode = modeMap.get(id)
          if (!mode) return null
          const available = modeAvailable(mode)
          const active = activeMode === mode.id
          return (
            <div
              key={mode.id}
              className={`${styles.modeCard} ${active ? styles.modeCardActive : ''} ${!available ? styles.modeCardDisabled : ''}`}
            >
              <div className={styles.modeCardHeader}>
                <div className={styles.modeName}>{mode.name}</div>
                {available ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              </div>
              <div className={styles.modeMeta}>
                <Badge color={available ? 'green' : 'gray'}>{available ? t('warp.available') : t('warp.unavailable')}</Badge>
                {mode.id === 'usque' && <Badge color="green">推荐</Badge>}
                <span>{mode.protocol}</span>
              </div>
              <p className={styles.modeDesc}>{mode.description}</p>
              {!mode.installed && mode.reason && (
                <p className={styles.modeReason}>💡 {mode.reason}</p>
              )}
              <div className={styles.modeTags}>
                {mode.proxy_types.map((proxy) => <span key={proxy}>{proxy}</span>)}
                {mode.requires_privilege && <span>{t('warp.requiresPrivilege')}</span>}
                {mode.docker_only && <span>{t('warp.dockerOnly')}</span>}
                {mode.id === 'external' && <span>{mode.configured ? t('warp.configured') : t('warp.notConfigured')}</span>}
              </div>
              {mode.external_proxy && <div className={styles.externalProxy}>{mode.external_proxy}</div>}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function WarpControlPanel({ warp, modes, config, acting, onEnable, onDisable }: {
  warp: WarpStatus | null
  modes: WarpModeInfo[]
  config: WarpConfigResponse | null
  acting: boolean
  onEnable: (params: { mode: string; socksPort: number; httpPort: number; endpoint?: string }) => Promise<void>
  onDisable: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('auto')
  const [socksPort, setSocksPort] = useState('1080')
  const [httpPort, setHttpPort] = useState('0')
  const [endpoint, setEndpoint] = useState('')
  const [externalProxy, setExternalProxy] = useState('')

  useEffect(() => {
    if (!config) return
    setMode(config.warp_mode || 'auto')
    setSocksPort(String(config.warp_socks_port || 1080))
    setHttpPort(String(config.warp_http_port || 0))
    setEndpoint(config.warp_endpoint || '')
    setExternalProxy(config.warp_external_proxy || '')
  }, [config])

  const active = warp?.status === 'enabled' || warp?.status === 'starting'
  const availableModes = modes.filter(modeAvailable).map((item) => item.id)

  const handleSubmit = useCallback(async () => {
    await onEnable({
      mode,
      socksPort: normalizePort(socksPort, 1080, 1),
      httpPort: normalizePort(httpPort, 0, 0),
      endpoint: endpoint.trim() || undefined,
    })
  }, [endpoint, httpPort, mode, onEnable, socksPort])

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><Settings size={18} />{t('warp.controlPanel')}</div>
        <Badge color={active ? 'green' : 'gray'}>{active ? t('warp.running') : t('warp.stopped')}</Badge>
      </div>

      <div className={styles.controlForm}>
        <div className={styles.formField}>
          <label className={styles.formLabel}>{t('warp.mode')}</label>
          <select className={styles.formSelect} value={mode} onChange={(e) => setMode(e.target.value)} disabled={active || acting}>
            <option value="auto">{t('warp.auto')}</option>
            {modes.map((item) => (
              <option key={item.id} value={item.id} disabled={!availableModes.includes(item.id)}>
                {item.name}{!item.installed ? ` (${t('warp.notInstalled')})` : item.id === 'external' && !item.configured ? ` (${t('warp.notConfigured')})` : ''}
              </option>
            ))}
          </select>
        </div>
        <Input label={t('warp.socksPort')} description={t('warp.portDesc')} type="number" min={1} max={65535} value={socksPort} onChange={(e) => setSocksPort(e.target.value)} disabled={active || acting} />
        <Input label={t('warp.httpPort')} description={t('warp.httpPortDesc')} type="number" min={0} max={65535} value={httpPort} onChange={(e) => setHttpPort(e.target.value)} disabled={active || acting} />
        <Input label={t('warp.endpoint')} description={t('warp.endpointDesc')} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={t('warp.endpointPlaceholder')} disabled={active || acting} />
        <Input label={t('warp.externalProxy')} description={t('warp.externalProxyDesc')} value={externalProxy} onChange={(e) => setExternalProxy(e.target.value)} placeholder="socks5://warp:1080" disabled />
      </div>

      <div className={styles.infoNote}>
        <HelpCircle size={14} />
        <span>{t('warp.runtimeNote')}</span>
      </div>

      <div className={styles.cardActions}>
        {active ? (
          <Button variant="danger" size="sm" icon={<ShieldOff size={14} />} loading={acting} onClick={() => void onDisable()}>
            {acting ? t('warp.disabling') : t('warp.disable')}
          </Button>
        ) : (
          <Button variant="primary" size="sm" icon={<Shield size={14} />} loading={acting} onClick={() => void handleSubmit()}>
            {acting ? t('warp.enabling') : t('warp.enable')}
          </Button>
        )}
      </div>
    </Card>
  )
}

function WarpAdvancedCard({ config, registering, onRegister }: {
  config: WarpConfigResponse | null
  registering: boolean
  onRegister: (backend: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [backend, setBackend] = useState('wgcf')

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><KeyRound size={18} />{t('warp.advancedCard')}</div>
        <Badge color={config?.has_license_key ? 'green' : 'gray'}>{config?.has_license_key ? t('warp.licenseConfigured') : t('warp.licenseMissing')}</Badge>
      </div>
      <div className={styles.advancedSection}>
        <StatusField icon={<KeyRound size={13} />} label={t('warp.licenseKey')} value={config?.has_license_key ? t('warp.configured') : t('warp.notConfigured')} />
        <StatusField icon={<ShieldCheck size={13} />} label={t('warp.teamToken')} value={config?.has_team_token ? t('warp.configured') : t('warp.notConfigured')} />
        <StatusField icon={<Wifi size={13} />} label={t('warp.bindAddress')} value={config?.warp_bind_address || '—'} />
        <StatusField icon={<Settings size={13} />} label={t('warp.startupTimeout')} value={config ? `${config.warp_startup_timeout}s` : '—'} />
        <StatusField icon={<Network size={13} />} label={t('warp.usqueTransport')} value={usqueTransportLabel(t, config?.warp_usque_transport)} />
        <StatusField icon={<Shield size={13} />} label={t('warp.proxyAuth')} value={config?.has_proxy_auth ? t('warp.hasProxyAuth') : t('warp.noProxyAuth')} />
        <StatusField icon={<Server size={13} />} label={t('warp.deviceName')} value={config?.warp_device_name || '—'} />
        <StatusField icon={<TerminalSquare size={13} />} label={t('warp.gostArgs')} value={config?.warp_gost_args || '—'} />
        <StatusField icon={<Server size={13} />} label={t('warp.usquePath')} value={config?.warp_usque_path || '—'} />
        <StatusField icon={<Settings size={13} />} label={t('warp.usqueConfig')} value={config?.warp_usque_config || '—'} />
      </div>
      <div className={styles.registerRow}>
        <select className={styles.formSelect} value={backend} onChange={(e) => setBackend(e.target.value)} disabled={registering}>
          <option value="wgcf">wgcf</option>
          <option value="usque">usque</option>
        </select>
        <Button variant="secondary" size="sm" icon={<KeyRound size={14} />} loading={registering} onClick={() => void onRegister(backend)}>
          {registering ? t('warp.registering') : t('warp.register')}
        </Button>
      </div>
    </Card>
  )
}


function WarpComponentsCard({ components, installingComponent, onInstall }: {
  components: WarpComponentInfo[]
  installingComponent: string | null
  onInstall: (name: string) => Promise<void>
}) {
  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><Package size={18} />WARP 组件</div>
        <Badge color="teal">{components.filter((comp) => comp.installed).length}/{components.length || 3} 已安装</Badge>
      </div>
      {components.length === 0 ? (
        <div className={styles.infoNote}><AlertCircle size={14} />组件状态暂不可用。</div>
      ) : (
        <div className={styles.componentsGrid}>
          {components.map((comp) => (
            <div key={comp.name} className={styles.componentItem}>
              <div className={styles.componentInfo}>
                <span className={styles.componentName}>{comp.name}</span>
                <span className={styles.componentStatus}>
                  {comp.source === 'system' && '系统预装'}
                  {comp.source === 'runtime' && (comp.version ? `v${comp.version}` : '已安装')}
                  {comp.source === 'not_installed' && '未安装'}
                </span>
              </div>
              <div className={styles.componentActions}>
                {comp.source === 'not_installed' && (
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Download size={14} />}
                    loading={installingComponent === comp.name}
                    disabled={installingComponent !== null}
                    onClick={() => void onInstall(comp.name)}
                  >
                    安装
                  </Button>
                )}
                {comp.source === 'runtime' && <Badge color="green">✓ 已安装</Badge>}
                {comp.source === 'system' && <Badge color="blue">✓ 预装</Badge>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function WarpEnvironmentCard({ warp, modes }: { warp: WarpStatus | null; modes: WarpModeInfo[] }) {
  const { t } = useTranslation()
  const dockerReady = modes.some((mode) => mode.docker_only && mode.installed)
  const privilegedModeReady = modes.some((mode) => mode.requires_privilege && mode.installed)

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><Container size={18} />{t('warp.environmentCard')}</div>
        <Badge color={dockerReady ? 'green' : 'gray'}>{dockerReady ? t('warp.docker') : t('warp.directRun')}</Badge>
      </div>
      <div className={styles.environmentGrid}>
        <StatusField icon={<Container size={13} />} label={t('warp.runtime')} value={dockerReady ? t('warp.dockerReady') : t('warp.directRun')} />
        <StatusField icon={<Settings size={13} />} label={t('warp.owner')} value={ownerLabel(t, warp?.owner)} />
        <StatusField icon={<Shield size={13} />} label={t('warp.privilege')} value={privilegedModeReady ? t('warp.available') : t('warp.unavailable')} />
      </div>
      <Link className={styles.docLink} to="/config">
        {t('warp.docsLink')} <ExternalLink size={13} />
      </Link>
    </Card>
  )
}

export function WarpPage() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [warp, setWarp] = useState<WarpStatus | null>(null)
  const [modes, setModes] = useState<WarpModeInfo[]>([])
  const [config, setConfig] = useState<WarpConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [acting, setActing] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [components, setComponents] = useState<WarpComponentInfo[]>([])
  const [installingComponent, setInstallingComponent] = useState<string | null>(null)

  const fetchComponents = useCallback(async () => {
    try {
      const res = await api.getWarpComponents()
      setComponents(res.components)
    } catch {
      // ignore component status failures
    }
  }, [])

  const loadAll = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const [status, modeInfo, cfg] = await Promise.all([
        api.getWarpStatus(),
        api.getWarpModes(),
        api.getWarpConfig(),
      ])
      setWarp(status)
      setModes(modeInfo.modes)
      setConfig(cfg)
    } catch (err) {
      setWarp(null)
      if (!silent) addToast('error', t('warp.fetchFailedWithMessage', { message: formatError(err) }))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [addToast, t])

  useEffect(() => { void loadAll(); void fetchComponents() }, [fetchComponents, loadAll])

  const handleEnable = useCallback(async (params: { mode: string; socksPort: number; httpPort: number; endpoint?: string }) => {
    setActing(true)
    try {
      const res = await api.enableWarp(params.mode, params.socksPort, params.endpoint, params.httpPort)
      addToast('success', t('warp.enableSuccess', { mode: res.mode || params.mode, ip: res.ip || '—' }))
      await loadAll(true)
    } catch (err) {
      addToast('error', t('warp.enableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [addToast, loadAll, t])

  const handleDisable = useCallback(async () => {
    setActing(true)
    try {
      await api.disableWarp()
      addToast('success', t('warp.disableSuccess'))
      await loadAll(true)
    } catch (err) {
      addToast('error', t('warp.disableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [addToast, loadAll, t])

  const handleInstallComponent = useCallback(async (name: string) => {
    setInstallingComponent(name)
    try {
      await api.installWarpComponent(name)
      addToast('success', `${name} 安装成功`)
      await Promise.all([fetchComponents(), loadAll(true)])
    } catch (err) {
      addToast('error', `${name} 安装失败：${formatError(err)}`)
    } finally {
      setInstallingComponent(null)
    }
  }, [addToast, fetchComponents, loadAll])

  const handleRegister = useCallback(async (backend: string) => {
    setRegistering(true)
    try {
      await api.registerWarp(backend)
      addToast('success', t('warp.registerSuccess'))
      await loadAll(true)
    } catch (err) {
      addToast('error', t('warp.registerFailed', { message: formatError(err) }))
    } finally {
      setRegistering(false)
    }
  }, [addToast, loadAll, t])

  return (
    <m.div className={styles.page} variants={staggerContainer} initial="initial" animate="animate">
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}><Shield size={22} />{t('warp.pageTitle')}</h1>
          <p className={styles.pageDesc}>{t('warp.pageSubtitle')}</p>
        </div>
        <Tooltip content={t('warp.refreshTip')} position="left">
          <Button variant="outline" size="sm" icon={<RefreshCw size={14} />} loading={refreshing} onClick={() => void loadAll(true)}>
            {t('dashboard.refresh')}
          </Button>
        </Tooltip>
      </m.div>

      <m.div variants={staggerItem}>
        <WarpStatusCard warp={warp} loading={loading} refreshing={refreshing} onRefresh={() => void loadAll(true)} />
      </m.div>
      <m.div variants={staggerItem}>
        <WarpModesCard modes={modes} activeMode={warp?.mode} />
      </m.div>
      <m.div variants={staggerItem}>
        <WarpControlPanel warp={warp} modes={modes} config={config} acting={acting} onEnable={handleEnable} onDisable={handleDisable} />
      </m.div>
      <m.div variants={staggerItem}>
        <WarpAdvancedCard config={config} registering={registering} onRegister={handleRegister} />
      </m.div>
      <m.div variants={staggerItem}>
        <WarpEnvironmentCard warp={warp} modes={modes} />
      </m.div>
      <m.div variants={staggerItem}>
        <WarpComponentsCard components={components} installingComponent={installingComponent} onInstall={handleInstallComponent} />
      </m.div>
    </m.div>
  )
}
