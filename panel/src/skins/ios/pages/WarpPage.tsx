/**
 * WARP 专属管理页面 - ios skin
 *
 * 提供 Cloudflare WARP 状态、模式选择、启停、可用模式和连通性测试。
 */

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { m } from 'framer-motion'
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Cloud,
  Container,
  Globe,
  Loader2,
  Network,
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
import { useNotificationStore } from '@core/stores/notificationStore'
import type { WarpConfigResponse, WarpModeInfo, WarpStatus, WarpTestResult } from '@core/types'

const MODE_OPTIONS = [
  { id: 'auto', label: '自动选择' },
  { id: 'wireproxy', label: 'WireProxy (用户态 WireGuard)' },
  { id: 'kernel', label: '内核 WireGuard' },
  { id: 'usque', label: 'MASQUE/QUIC 隧道' },
  { id: 'warp-cli', label: '官方客户端 + GOST' },
  { id: 'external', label: '外部代理容器' },
] as const

const MODE_FALLBACK: Record<string, Omit<WarpModeInfo, 'installed'>> = {
  wireproxy: {
    id: 'wireproxy',
    name: 'WireProxy (用户态 WireGuard)',
    protocol: 'wireguard',
    requires_privilege: false,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
    description: '用户态 WireGuard，部署简单，适合大多数本地和容器环境。',
  },
  kernel: {
    id: 'kernel',
    name: '内核 WireGuard',
    protocol: 'wireguard',
    requires_privilege: true,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
    description: '使用系统内核 WireGuard 接口，性能较高，需要网络权限。',
  },
  usque: {
    id: 'usque',
    name: 'MASQUE/QUIC 隧道',
    protocol: 'masque',
    requires_privilege: false,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
    description: '基于 MASQUE/QUIC 的 WARP 隧道，适合受限网络环境。',
  },
  'warp-cli': {
    id: 'warp-cli',
    name: '官方客户端 + GOST',
    protocol: 'warp-cli',
    requires_privilege: true,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
    description: '调用 Cloudflare 官方客户端，再通过 GOST 暴露代理端口。',
  },
  external: {
    id: 'external',
    name: '外部代理容器',
    protocol: 'external',
    requires_privilege: false,
    docker_only: true,
    proxy_types: ['socks5', 'http'],
    description: '连接外部已配置好的代理容器，由外部服务负责 WARP 隧道。',
  },
}

const STATUS_LABEL: Record<WarpStatus['status'], string> = {
  disabled: '已禁用',
  starting: '启动中',
  enabled: '已启用',
  stopping: '停止中',
  error: '错误',
}

const theme = {
  pagePadding: '34px 18px',
  headerPadding: '24px 22px',
  cardPadding: 20,
  card: '#ffffff',
  headerBg: 'linear-gradient(180deg, #ffffff 0%, #f7f9ff 100%)',
  border: '#e5e5ea',
  fieldBg: '#f2f2f7',
  fieldBorder: '#ececf2',
  modeBg: '#ffffff',
  badgeBg: '#f2f2f7',
  inputBg: '#f2f2f7',
  inputBorder: '#e5e5ea',
  tagBg: '#eef5ff',
  tagBorder: '#d6e8ff',
  tagText: '#007aff',
  text: '#111827',
  muted: '#6b7280',
  primary: '#007aff',
  info: '#5ac8fa',
  success: '#34c759',
  warning: '#ff9500',
  danger: '#ff3b30',
  successSoft: 'rgba(52, 199, 89, 0.12)',
  warningSoft: 'rgba(255, 149, 0, 0.12)',
  dangerSoft: 'rgba(255, 59, 48, 0.12)',
  surfaceMuted: '#f2f2f7',
  successBorder: 'rgba(52, 199, 89, 0.30)',
  warningBorder: 'rgba(255, 149, 0, 0.30)',
  dangerBorder: 'rgba(255, 59, 48, 0.30)',
  primaryButtonBg: '#007aff',
  primaryButtonBorder: '#007aff',
  primaryButtonText: '#ffffff',
  secondaryButtonBg: '#f2f2f7',
  radius: 28,
  fieldRadius: 18,
  inputRadius: 14,
  buttonRadius: 14,
  badgeRadius: 999,
  shadow: '0 12px 30px rgba(17, 24, 39, 0.08)',
  activeShadow: '0 0 0 4px rgba(0, 122, 255, 0.14)',
  titleSize: 34,
  titleWeight: 800,
  titleSpacing: '-0.035em',
  letterSpacing: '0.08em',
  inputPadding: '12px 14px',
} as const

function normalizePort(value: string, fallback: number, min = 0) {
  const n = Number.parseInt(value, 10)
  if (Number.isNaN(n)) return fallback
  return Math.min(Math.max(n, min), 65535)
}

function fallbackMode(id: string, warp: WarpStatus | null): WarpModeInfo {
  const statusModes = warp?.available_modes as Record<string, boolean> | undefined
  return {
    ...MODE_FALLBACK[id],
    installed: Boolean(statusModes?.[id]),
    configured: id === 'external' ? Boolean(statusModes?.[id]) : undefined,
  }
}

function modeAvailable(mode: WarpModeInfo) {
  return mode.installed && (mode.id !== 'external' || Boolean(mode.configured))
}

function displayMode(id?: string) {
  if (!id) return '—'
  return MODE_OPTIONS.find((mode) => mode.id === id)?.label || id
}

function statusColor(status?: WarpStatus['status']) {
  if (status === 'enabled') return theme.success
  if (status === 'error') return theme.danger
  if (status === 'starting' || status === 'stopping') return theme.warning
  return theme.muted
}

function resultMessage(result: WarpTestResult) {
  if (!result.ok) return '测试未通过，请检查当前 WARP 状态。'
  return `测试通过：出口 IP ${result.ip || '未知'}，模式 ${displayMode(result.mode)}，协议 ${result.protocol || '未知'}`
}

export function WarpPage() {
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
        addToast('error', `读取 WARP 状态失败：${formatError(statusResult.reason)}`)
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [addToast])

  useEffect(() => { void loadData() }, [loadData])

  const visibleModes = useMemo(() => {
    const modeMap = new Map(modes.map((item) => [item.id, item]))
    return MODE_OPTIONS.filter((item) => item.id !== 'auto').map((item) => modeMap.get(item.id) || fallbackMode(item.id, warp))
  }, [modes, warp])

  const handleEnable = useCallback(async () => {
    setActing(true)
    try {
      const res = await api.enableWarp(
        mode,
        normalizePort(socksPort, 1080, 1),
        endpoint.trim() || undefined,
        normalizePort(httpPort, 0, 0),
      )
      if (res.ok === false) throw new Error(res.error || res.message || '启用失败')
      addToast('success', `WARP 已启用：${displayMode(res.mode || mode)}${res.ip ? `，IP ${res.ip}` : ''}`)
      setTestResult(null)
      await loadData(true)
    } catch (err) {
      addToast('error', `启用 WARP 失败：${formatError(err)}`)
    } finally {
      setActing(false)
    }
  }, [addToast, endpoint, httpPort, loadData, mode, socksPort])

  const handleDisable = useCallback(async () => {
    setActing(true)
    try {
      const res = await api.disableWarp()
      if (res.ok === false) throw new Error(res.error || res.message || '禁用失败')
      addToast('success', 'WARP 已禁用')
      setTestResult(null)
      await loadData(true)
    } catch (err) {
      addToast('error', `禁用 WARP 失败：${formatError(err)}`)
    } finally {
      setActing(false)
    }
  }, [addToast, loadData])

  const handleTest = useCallback(async () => {
    setTesting(true)
    try {
      const result = await api.testWarp()
      setTestResult(result)
      addToast(result.ok ? 'success' : 'info', resultMessage(result))
    } catch (err) {
      addToast('error', `WARP 测试失败：${formatError(err)}`)
    } finally {
      setTesting(false)
    }
  }, [addToast])

  const enabled = warp?.status === 'enabled'
  const pending = warp?.status === 'starting' || warp?.status === 'stopping'

  if (loading) {
    return (
      <div style={styles.page}>
        <div style={styles.loading}><Loader2 size={18} /> 正在加载 WARP 管理信息…</div>
      </div>
    )
  }

  return (
    <m.div style={styles.page} variants={staggerContainer} initial="hidden" animate="show">
      <m.header style={styles.header} variants={staggerItem}>
        <div>
          <div style={styles.eyebrow}>Cloudflare WARP</div>
          <h1 style={styles.title}>WARP 管理</h1>
          <p style={styles.subtitle}>为搜索、抓取和数据源请求配置 WARP 代理模式，查看当前出口与运行状态。</p>
        </div>
        <button style={styles.secondaryButton} onClick={() => void loadData(true)} disabled={refreshing}>
          <RefreshCw size={16} /> {refreshing ? '刷新中…' : '刷新'}
        </button>
      </m.header>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<ShieldCheck size={19} />} title="当前状态" badge={STATUS_LABEL[warp?.status || 'disabled']} badgeColor={statusColor(warp?.status)} />
        {!warp ? (
          <Notice icon={<AlertTriangle size={15} />} tone="warning">WARP 状态暂不可用，请确认后端服务是否已启动。</Notice>
        ) : (
          <>
            <div style={styles.statusGrid}>
              <StatusField icon={<CircleDot size={14} />} label="运行状态" value={STATUS_LABEL[warp.status]} strong color={statusColor(warp.status)} />
              <StatusField icon={<Network size={14} />} label="当前模式" value={displayMode(warp.mode)} />
              <StatusField icon={<Globe size={14} />} label="WARP IP" value={warp.ip || '—'} />
              <StatusField icon={<Wifi size={14} />} label="SOCKS 端口" value={String(warp.socks_port || '—')} />
              <StatusField icon={<Cloud size={14} />} label="HTTP 端口" value={warp.http_port ? String(warp.http_port) : '关闭'} />
              <StatusField icon={<Route size={14} />} label="协议" value={warp.protocol || '—'} />
              <StatusField icon={<Server size={14} />} label="代理类型" value={warp.proxy_type || '—'} />
              <StatusField icon={<TerminalSquare size={14} />} label="进程 PID" value={warp.pid > 0 ? String(warp.pid) : '—'} />
            </div>
            {warp.last_error && <Notice icon={<AlertTriangle size={15} />} tone="danger">{warp.last_error}</Notice>}
            {testResult && (
              <Notice icon={testResult.ok ? <CheckCircle2 size={15} /> : <XCircle size={15} />} tone={testResult.ok ? 'success' : 'danger'}>
                {resultMessage(testResult)}
              </Notice>
            )}
            <div style={styles.actions}>
              <button style={styles.primaryButton} disabled={!enabled || testing} onClick={() => void handleTest()}>
                {testing ? <Loader2 size={16} /> : <Play size={16} />} {testing ? '测试中…' : '快速测试'}
              </button>
              <button style={styles.dangerButton} disabled={!enabled || pending || acting} onClick={() => void handleDisable()}>
                {acting ? <Loader2 size={16} /> : <ShieldOff size={16} />} 禁用 WARP
              </button>
            </div>
          </>
        )}
      </m.section>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<Power size={19} />} title="启用配置" badge="6 种模式" badgeColor={theme.primary} />
        <div style={styles.formGrid}>
          <label style={styles.formField}>
            <span style={styles.label}>模式选择</span>
            <select style={styles.input} value={mode} onChange={(event) => setMode(event.target.value)}>
              {MODE_OPTIONS.map((item) => { const info = modes.find((m) => m.id === item.id); const notInstalled = info && !info.installed; return <option key={item.id} value={item.id} disabled={notInstalled || false}>{item.label}{notInstalled ? " (未安装)" : ""}</option> })}
            </select>
          </label>
          <label style={styles.formField}>
            <span style={styles.label}>SOCKS 端口</span>
            <input style={styles.input} type="number" min={1} max={65535} value={socksPort} onChange={(event) => setSocksPort(event.target.value)} />
          </label>
          <label style={styles.formField}>
            <span style={styles.label}>HTTP 端口</span>
            <input style={styles.input} type="number" min={0} max={65535} value={httpPort} onChange={(event) => setHttpPort(event.target.value)} />
          </label>
          <label style={styles.formFieldWide}>
            <span style={styles.label}>自定义端点</span>
            <input style={styles.input} type="text" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="留空使用默认 WARP 端点" />
          </label>
        </div>
        <div style={styles.actions}>
          <button style={styles.primaryButton} disabled={acting || pending} onClick={() => void handleEnable()}>
            {acting ? <Loader2 size={16} /> : <Shield size={16} />} {acting ? '处理中…' : '启用 / 切换 WARP'}
          </button>
          <button style={styles.secondaryButton} disabled={refreshing} onClick={() => void loadData(true)}>
            <RefreshCw size={16} /> 重新读取配置
          </button>
        </div>
      </m.section>

      <m.section style={styles.card} variants={staggerItem}>
        <CardHeader icon={<Network size={19} />} title="可用模式" badge={`${visibleModes.filter(modeAvailable).length}/${visibleModes.length} 可用`} badgeColor={theme.info} />
        <div style={styles.modeGrid}>
          {visibleModes.map((item) => {
            const available = modeAvailable(item)
            const active = warp?.mode === item.id
            return (
              <div key={item.id} style={{ ...styles.modeCard, ...(active ? styles.modeCardActive : {}), ...(!available ? styles.modeCardDisabled : {}) }}>
                <div style={styles.modeHeader}>
                  <strong>{displayMode(item.id)}</strong>
                  <span style={{ ...styles.smallBadge, background: available ? theme.successSoft : theme.surfaceMuted, color: available ? theme.success : theme.muted }}>
                    {available ? '可用' : '不可用'}
                  </span>
                </div>
                <p style={styles.modeDesc}>{item.description}</p>
                {!item.installed && item.reason && (
                  <p style={styles.modeReason}>💡 {item.reason}</p>
                )}
                {item.id === 'usque' && <span style={styles.recommendedBadge}>推荐</span>}
                <div style={styles.tags}>
                  <span style={styles.tag}>{item.protocol || 'unknown'}</span>
                  {item.proxy_types.map((proxy) => <span key={proxy} style={styles.tag}>{proxy}</span>)}
                  {item.requires_privilege && <span style={styles.tag}>需要权限</span>}
                  {item.docker_only && <span style={styles.tag}>容器模式</span>}
                  {item.id === 'external' && <span style={styles.tag}>{item.configured ? '已配置' : '未配置'}</span>}
                </div>
                {item.external_proxy && <div style={styles.externalProxy}>{item.external_proxy}</div>}
              </div>
            )
          })}
        </div>
      </m.section>

      <m.section style={styles.split} variants={staggerItem}>
        <div style={styles.card}>
          <CardHeader icon={<Settings size={19} />} title="高级配置" />
          {config ? (
            <div style={styles.compactList}>
              <StatusField label="绑定地址" value={config.warp_bind_address || '—'} />
              <StatusField label="启动超时" value={`${config.warp_startup_timeout || 0} 秒`} />
              <StatusField label="设备名称" value={config.warp_device_name || '—'} />
              <StatusField label="USQUE 传输" value={config.warp_usque_transport || '—'} />
              <StatusField label="许可证" value={config.has_license_key ? '已配置' : '未配置'} />
              <StatusField label="团队令牌" value={config.has_team_token ? '已配置' : '未配置'} />
              <StatusField label="代理认证" value={config.has_proxy_auth ? '已配置' : '未配置'} />
              <StatusField label="外部代理" value={config.warp_external_proxy || '—'} />
            </div>
          ) : <Notice icon={<AlertTriangle size={15} />} tone="warning">高级配置暂不可用。</Notice>}
        </div>
        <div style={styles.card}>
          <CardHeader icon={<Container size={19} />} title="运行环境" />
          <div style={styles.compactList}>
            <StatusField label="控制方" value={warp?.owner || '—'} />
            <StatusField label="网络接口" value={warp?.interface || '—'} />
            <StatusField label="进程 PID" value={warp && warp.pid > 0 ? String(warp.pid) : '—'} />
            <StatusField label="已安装模式" value={`${visibleModes.filter((item) => item.installed).length} 个`} />
            <StatusField label="当前代理类型" value={warp?.proxy_type || '—'} />
          </div>
        </div>
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
