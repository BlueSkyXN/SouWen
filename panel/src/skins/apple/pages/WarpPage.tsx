/**
 * WARP 专属管理页面 - apple skin
 *
 * 提供 Cloudflare WARP 状态、模式选择、启停、可用模式和连通性测试。
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Cloud,
  Container,
  Globe,
  Loader2,
  Download,
  Network,
  Package,
  Play,
  Power,
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
import {
  WARP_MODE_OPTIONS,
  getDisplayWarpModes,
  getWarpModeLabel,
  isWarpModeInfoAvailable,
} from '@core/lib/warpModes'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { WarpComponentInfo, WarpConfigResponse, WarpModeInfo, WarpStatus, WarpTestResult } from '@core/types'

const theme = {
  pagePadding: '44px 24px',
  headerPadding: '30px 32px',
  cardPadding: 24,
  card: 'rgba(255, 255, 255, 0.88)',
  headerBg: 'linear-gradient(135deg, rgba(255,255,255,0.94) 0%, rgba(245,247,250,0.92) 100%)',
  border: 'rgba(0, 0, 0, 0.08)',
  fieldBg: 'rgba(245, 245, 247, 0.8)',
  fieldBorder: 'rgba(0, 0, 0, 0.06)',
  modeBg: 'rgba(255, 255, 255, 0.72)',
  badgeBg: 'rgba(245, 245, 247, 0.9)',
  inputBg: 'rgba(255, 255, 255, 0.9)',
  inputBorder: 'rgba(0, 0, 0, 0.12)',
  tagBg: 'rgba(0, 113, 227, 0.08)',
  tagBorder: 'rgba(0, 113, 227, 0.18)',
  tagText: '#0066cc',
  text: '#1d1d1f',
  muted: '#6e6e73',
  primary: '#0071e3',
  info: '#2997ff',
  success: '#248a3d',
  warning: '#a05a00',
  danger: '#d70015',
  successSoft: 'rgba(52, 199, 89, 0.12)',
  warningSoft: 'rgba(255, 159, 10, 0.12)',
  dangerSoft: 'rgba(255, 59, 48, 0.12)',
  surfaceMuted: 'rgba(142, 142, 147, 0.12)',
  successBorder: 'rgba(52, 199, 89, 0.28)',
  warningBorder: 'rgba(255, 159, 10, 0.28)',
  dangerBorder: 'rgba(255, 59, 48, 0.28)',
  primaryButtonBg: '#0071e3',
  primaryButtonBorder: '#0071e3',
  primaryButtonText: '#ffffff',
  secondaryButtonBg: 'rgba(245, 245, 247, 0.9)',
  radius: 24,
  fieldRadius: 16,
  inputRadius: 12,
  buttonRadius: 999,
  badgeRadius: 999,
  shadow: '0 18px 44px rgba(0, 0, 0, 0.08)',
  activeShadow: '0 0 0 4px rgba(0, 113, 227, 0.13)',
  titleSize: 40,
  titleWeight: 700,
  titleSpacing: '-0.045em',
  letterSpacing: '0.10em',
  inputPadding: '12px 14px',
} as const

function normalizePort(value: string, fallback: number, min = 0) {
  const n = Number.parseInt(value, 10)
  if (Number.isNaN(n)) return fallback
  return Math.min(Math.max(n, min), 65535)
}

function statusColor(status?: WarpStatus['status']) {
  if (status === 'enabled') return theme.success
  if (status === 'error') return theme.danger
  if (status === 'starting' || status === 'stopping') return theme.warning
  return theme.muted
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
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<WarpTestResult | null>(null)
  const [mode, setMode] = useState('auto')
  const [socksPort, setSocksPort] = useState('1080')
  const [httpPort, setHttpPort] = useState('0')
  const [endpoint, setEndpoint] = useState('')
  const [components, setComponents] = useState<WarpComponentInfo[]>([])
  const [installingComponent, setInstallingComponent] = useState<string | null>(null)
  const translateWarpMode = useCallback((key: string) => t(key), [t])
  const displayMode = useCallback((id?: string) => {
    if (!id) return '—'
    return getWarpModeLabel(id, translateWarpMode) || id
  }, [translateWarpMode])
  const resultMessage = useCallback((result: WarpTestResult) => {
    if (!result.ok) return t('warp.testNotPassed')
    return t('warp.testPassedDetailed', {
      ip: result.ip || t('warp.unknown'),
      mode: displayMode(result.mode),
      protocol: result.protocol || t('warp.unknown'),
    })
  }, [displayMode, t])

  const fetchComponents = useCallback(async () => {
    try {
      const res = await api.getWarpComponents()
      setComponents(res.components)
    } catch {
      // ignore component status failures
    }
  }, [])

  const loadData = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    else setLoading(true)
    try {
      const [statusResult, modesResult, configResult] = await Promise.allSettled([
        api.getWarpStatus(),
        api.getWarpModes(),
        api.getWarpConfig(),
      ])

      const nextWarp = statusResult.status === 'fulfilled' ? statusResult.value : null
      setWarp(nextWarp)

      if (modesResult.status === 'fulfilled') {
        setModes(modesResult.value.modes)
      } else {
        setModes([])
      }

      if (configResult.status === 'fulfilled') {
        const nextConfig = configResult.value
        setConfig(nextConfig)
        setMode(nextConfig.warp_mode || 'auto')
        setSocksPort(String(nextConfig.warp_socks_port || 1080))
        setHttpPort(String(nextConfig.warp_http_port ?? 0))
        setEndpoint(nextConfig.warp_endpoint || '')
      } else {
        setConfig(null)
      }

      if (statusResult.status === 'rejected' && !silent) {
        addToast('error', t('warp.fetchFailedWithMessage', { message: formatError(statusResult.reason) }))
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [addToast, t])

  useEffect(() => { void loadData(); void fetchComponents() }, [fetchComponents, loadData])

  const visibleModes = useMemo(() => {
    return getDisplayWarpModes(modes, warp, translateWarpMode)
  }, [modes, translateWarpMode, warp])

  const handleInstallComponent = useCallback(async (name: string) => {
    setInstallingComponent(name)
    try {
      await api.installWarpComponent(name)
      addToast('success', t('warp.componentInstallSuccess', { name }))
      await Promise.all([fetchComponents(), loadData(true)])
    } catch (err) {
      addToast('error', t('warp.componentInstallFailed', { name, message: formatError(err) }))
    } finally {
      setInstallingComponent(null)
    }
  }, [addToast, fetchComponents, loadData, t])

  const handleEnable = useCallback(async () => {
    setActing(true)
    try {
      const res = await api.enableWarp(
        mode,
        normalizePort(socksPort, 1080, 1),
        endpoint.trim() || undefined,
        normalizePort(httpPort, 0, 0),
      )
      if (res.ok === false) throw new Error(res.error || res.message || t('warp.unknown'))
      addToast('success', t('warp.enableSuccess', { mode: displayMode(res.mode || mode), ip: res.ip || '—' }))
      setTestResult(null)
      await loadData(true)
    } catch (err) {
      addToast('error', t('warp.enableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [addToast, displayMode, endpoint, httpPort, loadData, mode, socksPort, t])

  const handleDisable = useCallback(async () => {
    setActing(true)
    try {
      const res = await api.disableWarp()
      if (res.ok === false) throw new Error(res.error || res.message || t('warp.unknown'))
      addToast('success', t('warp.disableSuccess'))
      setTestResult(null)
      await loadData(true)
    } catch (err) {
      addToast('error', t('warp.disableFailed', { message: formatError(err) }))
    } finally {
      setActing(false)
    }
  }, [addToast, loadData, t])

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await api.testWarp()
      setTestResult(result)
      addToast(result.ok ? 'success' : 'info', resultMessage(result))
    } catch (err) {
      addToast('error', t('warp.testFailed', { message: formatError(err) }))
    } finally {
      setTesting(false)
    }
  }, [addToast, resultMessage, t])

  const enabled = warp?.status === 'enabled'
  const pending = warp?.status === 'starting' || warp?.status === 'stopping'

  if (loading) {
    return (
      <div style={styles.page}>
        <div style={styles.loading}><Loader2 size={18} /> {t('warp.loading')}</div>
      </div>
    )
  }

  return (
    <m.div style={styles.page} variants={staggerContainer} initial="hidden" animate="show">
      <m.header style={styles.header} variants={staggerItem}>
        <div>
          <div style={styles.eyebrow}>Cloudflare WARP</div>
          <h1 style={styles.title}>{t('warp.pageTitle')}</h1>
          <p style={styles.subtitle}>{t('warp.pageSubtitle')}</p>
        </div>
        <button style={styles.secondaryButton} onClick={() => void loadData(true)} disabled={refreshing}>
          <RefreshCw size={16} /> {refreshing ? t('warp.refreshing') : t('dashboard.refresh')}
        </button>
      </m.header>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<ShieldCheck size={19} />} title={t('warp.statusCard')} badge={t(`warp.${warp?.status || 'disabled'}`)} badgeColor={statusColor(warp?.status)} />
        {!warp ? (
          <Notice icon={<AlertTriangle size={15} />} tone="warning">{t('warp.statusUnavailable')}</Notice>
        ) : (
          <>
            <div style={styles.statusGrid}>
              <StatusField icon={<CircleDot size={14} />} label={t('warp.status')} value={t(`warp.${warp.status}`)} strong color={statusColor(warp.status)} />
              <StatusField icon={<Network size={14} />} label={t('warp.mode')} value={displayMode(warp.mode)} />
              <StatusField icon={<Globe size={14} />} label={t('warp.ip')} value={warp.ip || '—'} />
              <StatusField icon={<Wifi size={14} />} label={t('warp.socksPort')} value={String(warp.socks_port || '—')} />
              <StatusField icon={<Cloud size={14} />} label={t('warp.httpPort')} value={warp.http_port ? String(warp.http_port) : t('warp.disabledShort')} />
              <StatusField icon={<Route size={14} />} label={t('warp.protocol')} value={warp.protocol || '—'} />
              <StatusField icon={<Server size={14} />} label={t('warp.proxyType')} value={warp.proxy_type || '—'} />
              <StatusField icon={<TerminalSquare size={14} />} label={t('warp.pid')} value={warp.pid > 0 ? String(warp.pid) : '—'} />
            </div>
            {warp.last_error && <Notice icon={<AlertTriangle size={15} />} tone="danger">{warp.last_error}</Notice>}
            {testResult && (
              <Notice icon={testResult.ok ? <CheckCircle2 size={15} /> : <XCircle size={15} />} tone={testResult.ok ? 'success' : 'danger'}>
                {resultMessage(testResult)}
              </Notice>
            )}
            <div style={styles.actions}>
              <button style={styles.primaryButton} disabled={!enabled || testing} onClick={() => void handleTest()}>
                {testing ? <Loader2 size={16} /> : <Play size={16} />} {testing ? t('warp.testing') : t('warp.testConnection')}
              </button>
              <button style={styles.dangerButton} disabled={!enabled || pending || acting} onClick={() => void handleDisable()}>
                {acting ? <Loader2 size={16} /> : <ShieldOff size={16} />} {t('warp.disable')}
              </button>
            </div>
          </>
        )}
      </m.section>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<Power size={19} />} title={t('warp.controlPanel')} badge={t('warp.modeCount', { count: WARP_MODE_OPTIONS.length })} badgeColor={theme.primary} />
        <div style={styles.formGrid}>
          <label style={styles.formField}>
            <span style={styles.label}>{t('warp.mode')}</span>
            <select style={styles.input} value={mode} onChange={(event) => setMode(event.target.value)}>
              {WARP_MODE_OPTIONS.map((item) => {
                const info = modes.find((m) => m.id === item.value)
                const unavailable = info ? !isWarpModeInfoAvailable(info) : false
                const notInstalled = info && !info.installed
                return <option key={item.value} value={item.value} disabled={unavailable}>{t(item.labelKey)}{notInstalled ? ` (${t('warp.notInstalled')})` : ''}</option>
              })}
            </select>
          </label>
          <label style={styles.formField}>
            <span style={styles.label}>{t('warp.socksPort')}</span>
            <input style={styles.input} type="number" min={1} max={65535} value={socksPort} onChange={(event) => setSocksPort(event.target.value)} />
          </label>
          <label style={styles.formField}>
            <span style={styles.label}>{t('warp.httpPort')}</span>
            <input style={styles.input} type="number" min={0} max={65535} value={httpPort} onChange={(event) => setHttpPort(event.target.value)} />
          </label>
          <label style={styles.formFieldWide}>
            <span style={styles.label}>{t('warp.endpoint')}</span>
            <input style={styles.input} type="text" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder={t('warp.endpointPlaceholder')} />
          </label>
        </div>
        <div style={styles.actions}>
          <button style={styles.primaryButton} disabled={acting || pending} onClick={() => void handleEnable()}>
            {acting ? <Loader2 size={16} /> : <Shield size={16} />} {acting ? t('warp.processing') : t('warp.enableSwitch')}
          </button>
          <button style={styles.secondaryButton} disabled={refreshing} onClick={() => void loadData(true)}>
            <RefreshCw size={16} /> {t('dashboard.refresh')}
          </button>
        </div>
      </m.section>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<Network size={19} />} title={t('warp.modesCard')} badge={t('warp.availableModeCount', { available: visibleModes.filter(isWarpModeInfoAvailable).length, total: visibleModes.length })} badgeColor={theme.info} />
        <div style={styles.modeGrid}>
          {visibleModes.map((item) => {
            const available = isWarpModeInfoAvailable(item)
            const active = warp?.mode === item.id
            return (
              <div key={item.id} style={{ ...styles.modeCard, ...(active ? styles.modeCardActive : {}), ...(!available ? styles.modeCardDisabled : {}) }}>
                <div style={styles.modeHeader}>
                  <strong>{displayMode(item.id)}</strong>
                  <span style={{ ...styles.smallBadge, background: available ? theme.successSoft : theme.surfaceMuted, color: available ? theme.success : theme.muted }}>
                    {available ? t('warp.available') : t('warp.unavailable')}
                  </span>
                </div>
                <p style={styles.modeDesc}>{item.description}</p>
                {!item.installed && item.reason && (
                  <p style={styles.modeReason}>💡 {item.reason}</p>
                )}
                {item.id === 'usque' && <span style={styles.recommendedBadge}>{t('warp.recommended')}</span>}
                <div style={styles.tags}>
                  <span style={styles.tag}>{item.protocol || t('warp.unknown')}</span>
                  {item.proxy_types.map((proxy) => <span key={proxy} style={styles.tag}>{proxy}</span>)}
                  {item.requires_privilege && <span style={styles.tag}>{t('warp.requiresPrivilege')}</span>}
                  {item.docker_only && <span style={styles.tag}>{t('warp.dockerOnly')}</span>}
                  {item.id === 'external' && <span style={styles.tag}>{item.configured ? t('warp.configured') : t('warp.notConfigured')}</span>}
                </div>
                {item.external_proxy && <div style={styles.externalProxy}>{item.external_proxy}</div>}
              </div>
            )
          })}
        </div>
      </m.section>

      <m.section style={styles.split} variants={staggerItem}>
        <div style={styles.card}>
          <CardHeader icon={<Settings size={19} />} title={t('warp.advancedCard')} />
          {config ? (
            <div style={styles.compactList}>
              <StatusField label={t('warp.bindAddress')} value={config.warp_bind_address || '—'} />
              <StatusField label={t('warp.startupTimeout')} value={t('warp.seconds', { count: config.warp_startup_timeout || 0 })} />
              <StatusField label={t('warp.deviceName')} value={config.warp_device_name || '—'} />
              <StatusField label={t('warp.usqueTransport')} value={config.warp_usque_transport || '—'} />
              <StatusField label={t('warp.licenseKey')} value={config.has_license_key ? t('warp.configured') : t('warp.notConfigured')} />
              <StatusField label={t('warp.teamToken')} value={config.has_team_token ? t('warp.configured') : t('warp.notConfigured')} />
              <StatusField label={t('warp.proxyAuth')} value={config.has_proxy_auth ? t('warp.configured') : t('warp.notConfigured')} />
              <StatusField label={t('warp.externalProxy')} value={config.warp_external_proxy || '—'} />
            </div>
          ) : <Notice icon={<AlertTriangle size={15} />} tone="warning">{t('warp.advancedUnavailable')}</Notice>}
        </div>
        <div style={styles.card}>
          <CardHeader icon={<Container size={19} />} title={t('warp.environmentCard')} />
          <div style={styles.compactList}>
            <StatusField label={t('warp.owner')} value={warp?.owner || '—'} />
            <StatusField label={t('warp.interface')} value={warp?.interface || '—'} />
            <StatusField label={t('warp.pid')} value={warp && warp.pid > 0 ? String(warp.pid) : '—'} />
            <StatusField label={t('warp.installedModes')} value={t('warp.itemCount', { count: visibleModes.filter((item) => item.installed).length })} />
            <StatusField label={t('warp.currentProxyType')} value={warp?.proxy_type || '—'} />
          </div>
        </div>
      </m.section>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<Package size={19} />} title={t('warp.componentsCard')} badge={t('warp.componentsInstalledCount', { installed: components.filter((comp) => comp.installed).length, total: components.length || 3 })} badgeColor={theme.success} />
        {components.length === 0 ? (
          <Notice icon={<AlertTriangle size={15} />} tone="warning">{t('warp.componentsUnavailable')}</Notice>
        ) : (
          <div style={styles.componentList}>
            {components.map((comp) => (
              <div key={comp.name} style={styles.componentRow}>
                <div style={styles.componentInfo}>
                  <span style={styles.componentName}>{comp.name}</span>
                  <span style={styles.componentStatus}>
                    {comp.source === 'system' && t('warp.systemPreinstalled')}
                    {comp.source === 'runtime' && (comp.version ? `v${comp.version}` : t('warp.installed'))}
                    {comp.source === 'not_installed' && t('warp.notInstalled')}
                  </span>
                </div>
                <div style={styles.componentActions}>
                  {comp.source === 'not_installed' && (
                    <button
                      style={styles.installButton}
                      onClick={() => void handleInstallComponent(comp.name)}
                      disabled={installingComponent !== null}
                    >
                      {installingComponent === comp.name ? <Loader2 size={15} /> : <Download size={15} />}
                      {t('warp.install')}
                    </button>
                  )}
                  {comp.source === 'runtime' && <span style={styles.installedMark}>✓ {t('warp.installed')}</span>}
                  {comp.source === 'system' && <span style={styles.preinstalledMark}>✓ {t('warp.preinstalled')}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </m.section>
    </m.div>
  )
}

function CardHeader({ icon, title, badge, badgeColor }: { icon: ReactNode; title: string; badge?: string; badgeColor?: string }) {
  return (
    <div style={styles.cardHeader}>
      <div style={styles.cardTitle}>{icon}{title}</div>
      {badge && <span style={{ ...styles.badge, color: badgeColor || theme.text, borderColor: badgeColor || theme.border }}>{badge}</span>}
    </div>
  )
}

function StatusField({ icon, label, value, strong, color }: { icon?: ReactNode; label: string; value: string; strong?: boolean; color?: string }) {
  return (
    <div style={styles.statusField}>
      <span style={styles.statusLabel}>{icon}{label}</span>
      <span style={{ ...styles.statusValue, ...(strong ? styles.statusValueStrong : {}), ...(color ? { color } : {}) }}>{value}</span>
    </div>
  )
}

function Notice({ icon, tone, children }: { icon: ReactNode; tone: 'success' | 'warning' | 'danger'; children: ReactNode }) {
  const palette = tone === 'success'
    ? { bg: theme.successSoft, fg: theme.success, bd: theme.successBorder }
    : tone === 'danger'
      ? { bg: theme.dangerSoft, fg: theme.danger, bd: theme.dangerBorder }
      : { bg: theme.warningSoft, fg: theme.warning, bd: theme.warningBorder }
  return <div style={{ ...styles.notice, background: palette.bg, color: palette.fg, borderColor: palette.bd }}>{icon}<span>{children}</span></div>
}

function makeStyles(): Record<string, CSSProperties> {
  return {
    page: {
      maxWidth: 1120,
      margin: '0 auto',
      padding: theme.pagePadding,
      color: theme.text,
      display: 'flex',
      flexDirection: 'column',
      gap: 24,
    },
    loading: {
      minHeight: 240,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 10,
      color: theme.muted,
      background: theme.card,
      border: `1px solid ${theme.border}`,
      borderRadius: theme.radius,
    },
    header: {
      display: 'flex',
      alignItems: 'flex-end',
      justifyContent: 'space-between',
      gap: 18,
      flexWrap: 'wrap',
      padding: theme.headerPadding,
      background: theme.headerBg,
      border: `1px solid ${theme.border}`,
      borderRadius: theme.radius,
      boxShadow: theme.shadow,
    },
    eyebrow: {
      color: theme.primary,
      fontSize: 12,
      fontWeight: 700,
      letterSpacing: theme.letterSpacing,
      textTransform: 'uppercase',
      marginBottom: 8,
    },
    title: {
      margin: 0,
      fontSize: theme.titleSize,
      lineHeight: 1.08,
      fontWeight: theme.titleWeight,
      letterSpacing: theme.titleSpacing,
    },
    subtitle: {
      margin: '10px 0 0',
      color: theme.muted,
      maxWidth: 680,
      lineHeight: 1.65,
      fontSize: 15,
    },
    card: {
      background: theme.card,
      border: `1px solid ${theme.border}`,
      borderRadius: theme.radius,
      padding: theme.cardPadding,
      boxShadow: theme.shadow,
    },
    split: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
      gap: 24,
    },
    cardHeader: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 12,
      marginBottom: 18,
      flexWrap: 'wrap',
    },
    cardTitle: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      fontSize: 18,
      fontWeight: 700,
      color: theme.text,
    },
    badge: {
      border: '1px solid',
      borderRadius: theme.badgeRadius,
      padding: '5px 10px',
      fontSize: 12,
      fontWeight: 700,
      background: theme.badgeBg,
    },
    smallBadge: {
      borderRadius: theme.badgeRadius,
      padding: '4px 8px',
      fontSize: 12,
      fontWeight: 700,
    },
    statusGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
      gap: 12,
    },
    statusField: {
      display: 'flex',
      flexDirection: 'column',
      gap: 7,
      padding: '13px 14px',
      background: theme.fieldBg,
      border: `1px solid ${theme.fieldBorder}`,
      borderRadius: theme.fieldRadius,
      minWidth: 0,
    },
    statusLabel: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      color: theme.muted,
      fontSize: 12,
      lineHeight: 1.2,
    },
    statusValue: {
      color: theme.text,
      fontSize: 14,
      fontWeight: 600,
      wordBreak: 'break-word',
    },
    statusValueStrong: {
      fontSize: 16,
      fontWeight: 800,
    },
    notice: {
      display: 'flex',
      gap: 9,
      alignItems: 'flex-start',
      marginTop: 14,
      padding: '12px 14px',
      border: '1px solid',
      borderRadius: theme.fieldRadius,
      fontSize: 13,
      lineHeight: 1.55,
    },
    actions: {
      display: 'flex',
      gap: 12,
      flexWrap: 'wrap',
      marginTop: 18,
    },
    primaryButton: {
      ...buttonBase(),
      color: theme.primaryButtonText,
      background: theme.primaryButtonBg,
      border: `1px solid ${theme.primaryButtonBorder}`,
    },
    secondaryButton: {
      ...buttonBase(),
      color: theme.text,
      background: theme.secondaryButtonBg,
      border: `1px solid ${theme.border}`,
    },
    dangerButton: {
      ...buttonBase(),
      color: theme.danger,
      background: theme.dangerSoft,
      border: `1px solid ${theme.dangerBorder}`,
    },
    formGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
      gap: 14,
    },
    formField: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    },
    formFieldWide: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      gridColumn: '1 / -1',
    },
    label: {
      fontSize: 13,
      color: theme.muted,
      fontWeight: 700,
    },
    input: {
      width: '100%',
      boxSizing: 'border-box',
      border: `1px solid ${theme.inputBorder}`,
      borderRadius: theme.inputRadius,
      background: theme.inputBg,
      color: theme.text,
      padding: theme.inputPadding,
      fontSize: 14,
      outline: 'none',
    },
    modeGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
      gap: 14,
    },
    modeCard: {
      padding: 16,
      borderRadius: theme.fieldRadius,
      border: `1px solid ${theme.fieldBorder}`,
      background: theme.modeBg,
      minHeight: 170,
    },
    modeCardActive: {
      borderColor: theme.primary,
      boxShadow: theme.activeShadow,
    },
    modeCardDisabled: {
      opacity: 0.62,
    },
    modeHeader: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 10,
      alignItems: 'flex-start',
      color: theme.text,
      lineHeight: 1.35,
    },
    modeDesc: {
      color: theme.muted,
      lineHeight: 1.6,
      fontSize: 13,
      margin: '12px 0',
    },
    modeReason: {
      color: theme.muted,
      lineHeight: 1.5,
      fontSize: 12,
      margin: '-6px 0 10px',
    },
    recommendedBadge: {
      display: 'inline-flex',
      alignSelf: 'flex-start',
      width: 'fit-content',
      color: theme.success,
      background: theme.successSoft,
      border: `1px solid ${theme.successBorder}`,
      borderRadius: theme.badgeRadius,
      padding: '3px 8px',
      fontSize: 11,
      fontWeight: 700,
      margin: '-4px 0 10px',
    },
    tags: {
      display: 'flex',
      gap: 6,
      flexWrap: 'wrap',
    },
    tag: {
      fontSize: 11,
      color: theme.tagText,
      background: theme.tagBg,
      border: `1px solid ${theme.tagBorder}`,
      borderRadius: theme.badgeRadius,
      padding: '4px 7px',
    },
    externalProxy: {
      marginTop: 10,
      padding: '8px 10px',
      color: theme.muted,
      background: theme.fieldBg,
      borderRadius: theme.fieldRadius,
      fontSize: 12,
      wordBreak: 'break-all',
    },
    compactList: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
      gap: 10,
    },

    componentList: {
      display: 'grid',
      gap: 12,
    },
    componentRow: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 14,
      padding: '13px 14px',
      background: theme.fieldBg,
      border: `1px solid ${theme.fieldBorder}`,
      borderRadius: theme.fieldRadius,
      flexWrap: 'wrap',
    },
    componentInfo: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      minWidth: 0,
    },
    componentName: {
      color: theme.text,
      fontSize: 15,
      fontWeight: 800,
      fontFamily: 'monospace',
    },
    componentStatus: {
      color: theme.muted,
      fontSize: 12,
      fontWeight: 700,
    },
    componentActions: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginLeft: 'auto',
    },
    installButton: {
      ...buttonBase(),
      minHeight: 34,
      padding: '0 12px',
      fontSize: 13,
      color: theme.primaryButtonText,
      background: theme.primaryButtonBg,
      border: `1px solid ${theme.primaryButtonBorder}`,
    },
    installedMark: {
      color: theme.success,
      background: theme.successSoft,
      border: `1px solid ${theme.successBorder}`,
      borderRadius: theme.badgeRadius,
      padding: '5px 9px',
      fontSize: 12,
      fontWeight: 800,
    },
    preinstalledMark: {
      color: theme.info,
      background: theme.surfaceMuted,
      border: `1px solid ${theme.border}`,
      borderRadius: theme.badgeRadius,
      padding: '5px 9px',
      fontSize: 12,
      fontWeight: 800,
    },
  }
}

function buttonBase(): CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    minHeight: 40,
    borderRadius: theme.buttonRadius,
    padding: '0 16px',
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
  }
}

const styles = makeStyles()
