/**
 * 文件用途：插件管理共享面板组件 — 5 个皮肤的 PluginsPage 都基于此组件渲染。
 *
 * 设计原则：
 *   - 数据 / 副作用：完全交给 usePluginsPage hook（参见 @core/hooks/usePluginsPage）
 *   - 视觉风格：使用 CSS 变量（var(--bg) / var(--text) / var(--accent) 等），
 *               跟随皮肤主题；不写硬编码颜色
 *   - 可访问性：所有按钮加 aria-label / disabled，禁用状态明确反馈
 *   - 安装入口：后端未启用 install_enabled 时禁用操作，并给出服务端配置提示
 *
 * 公共 Props 暂时只暴露 className，让皮肤可以用自己的容器约束布局。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  RefreshCw,
  Power,
  PowerOff,
  HeartPulse,
  PackagePlus,
  PackageMinus,
  Info,
  X,
  AlertTriangle,
  PlugZap,
  Tag,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { usePluginsPage } from '@core/hooks/usePluginsPage'
import type { PluginInfo, PluginHealthResponse } from '@core/types'
import styles from './PluginsPanel.module.scss'

interface PluginsPanelProps {
  className?: string
}

export function PluginsPanel({ className }: PluginsPanelProps) {
  const { t } = useTranslation()
  const state = usePluginsPage()
  const [detail, setDetail] = useState<PluginInfo | null>(null)
  const [pkgInput, setPkgInput] = useState('')
  const { installPackage, uninstallPackage } = state

  const handleInstall = useCallback(async () => {
    const ok = await installPackage(pkgInput)
    if (ok) setPkgInput('')
  }, [installPackage, pkgInput])

  const handleUninstall = useCallback(async () => {
    const ok = await uninstallPackage(pkgInput)
    if (ok) setPkgInput('')
  }, [pkgInput, uninstallPackage])

  return (
    <div className={`${styles.panel}${className ? ` ${className}` : ''}`}>
      {state.restartRequired && (
        <div className={styles.restartBanner} role="status">
          <AlertTriangle size={16} aria-hidden />
          <span>{t('plugins.restartBanner')}</span>
        </div>
      )}

      <header className={styles.toolbar}>
        <button
          type="button"
          className={styles.toolbarBtn}
          onClick={() => void state.refresh()}
          disabled={state.loading}
          aria-label={t('plugins.refresh') as string}
        >
          <RefreshCw size={14} className={state.loading ? styles.spinning : undefined} />
          <span>{state.loading ? t('plugins.refreshing') : t('plugins.refresh')}</span>
        </button>
        <button
          type="button"
          className={styles.toolbarBtn}
          onClick={() => void state.reloadPlugins()}
          disabled={state.busy.has('reload')}
        >
          <PlugZap size={14} />
          <span>{state.busy.has('reload') ? t('plugins.reloading') : t('plugins.reloadCatalog')}</span>
        </button>
      </header>

      {state.error && !state.loading ? (
        <div className={styles.error}>
          <XCircle size={16} aria-hidden />
          <span>{t('plugins.loadFailed', { message: state.error })}</span>
        </div>
      ) : null}

      {state.loading && state.plugins.length === 0 ? (
        <p className={styles.emptyState}>{t('plugins.loading')}</p>
      ) : null}

      {!state.loading && state.plugins.length === 0 && !state.error ? (
        <p className={styles.emptyState}>{t('plugins.empty')}</p>
      ) : null}

      {state.plugins.length > 0 && (
        <PluginsTable
          plugins={state.plugins}
          state={state}
          onShowDetail={setDetail}
        />
      )}

      <InstallCard
        installEnabled={state.installEnabled}
        installBusy={state.busy.has('install')}
        uninstallBusy={state.busy.has('uninstall')}
        pkgInput={pkgInput}
        onPkgChange={setPkgInput}
        onInstall={handleInstall}
        onUninstall={handleUninstall}
      />

      {detail !== null && (
        <DetailDialog
          plugin={detail}
          health={state.healthMap[detail.name]}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  )
}

interface PluginsTableProps {
  plugins: PluginInfo[]
  state: ReturnType<typeof usePluginsPage>
  onShowDetail: (plugin: PluginInfo) => void
}

function PluginsTable({ plugins, state, onShowDetail }: PluginsTableProps) {
  const { t } = useTranslation()
  return (
    <div className={styles.tableWrap} role="region" aria-label={t('plugins.title') as string}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{t('plugins.columns.name')}</th>
            <th>{t('plugins.columns.status')}</th>
            <th>{t('plugins.columns.source')}</th>
            <th>{t('plugins.columns.version')}</th>
            <th>{t('plugins.columns.health')}</th>
            <th>{t('plugins.columns.description')}</th>
            <th>{t('plugins.columns.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {plugins.map((p) => (
            <PluginRow
              key={p.name}
              plugin={p}
              state={state}
              onShowDetail={() => onShowDetail(p)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface PluginRowProps {
  plugin: PluginInfo
  state: ReturnType<typeof usePluginsPage>
  onShowDetail: () => void
}

function PluginRow({ plugin, state, onShowDetail }: PluginRowProps) {
  const { t } = useTranslation()
  const enableBusy = state.busy.has(`enable:${plugin.name}`)
  const disableBusy = state.busy.has(`disable:${plugin.name}`)
  const healthBusy = state.busy.has(`health:${plugin.name}`)
  const installBusy = state.busy.has('install')
  const packageBusy = installBusy || state.busy.has('uninstall')
  const isLoaded = plugin.status === 'loaded'
  const isDisabled = plugin.status === 'disabled'
  const isAvailable = plugin.status === 'available'

  const statusKey = ['loaded', 'available', 'disabled', 'error'].includes(plugin.status)
    ? plugin.status
    : 'unknown'
  const sourceKey = ['entry_point', 'catalog', 'config_path'].includes(plugin.source)
    ? plugin.source
    : 'unknown'

  return (
    <tr>
      <td className={styles.nameCell}>
        <span className={styles.nameText}>{plugin.name}</span>
        {plugin.first_party && <Tag size={12} className={styles.firstPartyBadge} aria-label={t('plugins.actions.firstParty') as string} />}
      </td>
      <td>
        <StatusPill status={statusKey} label={t(`plugins.status.${statusKey}`) as string} />
      </td>
      <td>
        <span className={styles.sourceText}>{t(`plugins.source.${sourceKey}`)}</span>
      </td>
      <td className={styles.versionCell}>{plugin.version || '—'}</td>
      <td>
        <HealthCell
          status={plugin.status}
          response={state.healthMap[plugin.name]}
          busy={healthBusy}
        />
      </td>
      <td className={styles.descCell}>{plugin.description || '—'}</td>
      <td className={styles.actionsCell}>
        {isLoaded && (
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.warn}`}
            onClick={() => void state.disablePlugin(plugin.name)}
            disabled={disableBusy}
            title={t('plugins.actions.disable') as string}
          >
            <PowerOff size={14} />
            <span>{t('plugins.actions.disable')}</span>
          </button>
        )}
        {isAvailable && plugin.package && (
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.primary}`}
            onClick={() => void state.installPackage(plugin.package as string)}
            disabled={!state.installEnabled || packageBusy}
            title={
              state.installEnabled
                ? (t('plugins.actions.install') as string)
                : (t('plugins.actions.configureInstall') as string)
            }
          >
            <PackagePlus size={14} />
            <span>{installBusy ? t('plugins.install.installing') : t('plugins.actions.install')}</span>
          </button>
        )}
        {isDisabled && (
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.primary}`}
            onClick={() => void state.enablePlugin(plugin.name)}
            disabled={enableBusy}
            title={t('plugins.actions.enable') as string}
          >
            <Power size={14} />
            <span>{t('plugins.actions.enable')}</span>
          </button>
        )}
        {isLoaded && (
          <button
            type="button"
            className={styles.actionBtn}
            onClick={() => void state.checkHealth(plugin.name)}
            disabled={healthBusy}
            title={t('plugins.actions.checkHealth') as string}
          >
            <HeartPulse size={14} />
            <span>{healthBusy ? t('plugins.health.running') : t('plugins.actions.checkHealth')}</span>
          </button>
        )}
        <button
          type="button"
          className={styles.actionBtn}
          onClick={onShowDetail}
          title={t('plugins.actions.viewDetail') as string}
        >
          <Info size={14} />
          <span>{t('plugins.actions.viewDetail')}</span>
        </button>
      </td>
    </tr>
  )
}

interface StatusPillProps {
  status: string
  label: string
}

function StatusPill({ status, label }: StatusPillProps) {
  const cls =
    status === 'loaded'
      ? styles.pillLoaded
      : status === 'available'
        ? styles.pillAvailable
        : status === 'disabled'
          ? styles.pillDisabled
          : status === 'error'
            ? styles.pillError
            : styles.pillUnknown
  return <span className={`${styles.pill} ${cls}`}>{label}</span>
}

interface HealthCellProps {
  status: string
  response?: PluginHealthResponse
  busy: boolean
}

function HealthCell({ status, response, busy }: HealthCellProps) {
  const { t } = useTranslation()
  if (status !== 'loaded') return <span className={styles.dim}>{t('plugins.health.unknown')}</span>
  if (busy) return <span className={styles.dim}>{t('plugins.health.running')}</span>
  if (!response) return <span className={styles.dim}>—</span>
  const state = String(response.status).toLowerCase()
  if (state === 'ok' || state === 'healthy') {
    return <span className={styles.healthOk}>{t('plugins.health.ok')}</span>
  }
  if (state === 'degraded' || state === 'warn' || state === 'warning') {
    return <span className={styles.healthDegraded}>{t('plugins.health.degraded')}</span>
  }
  return <span className={styles.healthError}>{t('plugins.health.error')}</span>
}

interface InstallCardProps {
  installEnabled: boolean
  installBusy: boolean
  uninstallBusy: boolean
  pkgInput: string
  onPkgChange: (v: string) => void
  onInstall: () => void
  onUninstall: () => void
}

function InstallCard({
  installEnabled,
  installBusy,
  uninstallBusy,
  pkgInput,
  onPkgChange,
  onInstall,
  onUninstall,
}: InstallCardProps) {
  const { t } = useTranslation()
  const packageBusy = installBusy || uninstallBusy
  return (
    <section className={styles.installCard} aria-label={t('plugins.install.panelTitle') as string}>
      <header className={styles.installHeader}>
        <h3 className={styles.installTitle}>{t('plugins.install.panelTitle')}</h3>
        {!installEnabled && <span className={styles.disabledHint}>{t('plugins.install.disabledHint')}</span>}
      </header>
      <p className={styles.installDesc}>{t('plugins.install.panelDesc')}</p>
      <div className={styles.installRow}>
        <label htmlFor="souwen-plugin-pkg" className={styles.installLabel}>
          {t('plugins.install.packageLabel')}
        </label>
        <input
          id="souwen-plugin-pkg"
          type="text"
          className={styles.installInput}
          value={pkgInput}
          placeholder={t('plugins.install.packagePlaceholder') as string}
          onChange={(e) => onPkgChange(e.target.value)}
          disabled={!installEnabled || packageBusy}
        />
        <button
          type="button"
          className={`${styles.actionBtn} ${styles.primary}`}
          onClick={onInstall}
          disabled={!installEnabled || packageBusy || !pkgInput.trim()}
          title={t('plugins.install.submitInstall') as string}
        >
          <PackagePlus size={14} />
          <span>{installBusy ? t('plugins.install.installing') : t('plugins.install.submitInstall')}</span>
        </button>
        <button
          type="button"
          className={`${styles.actionBtn} ${styles.warn}`}
          onClick={onUninstall}
          disabled={!installEnabled || packageBusy || !pkgInput.trim()}
          title={t('plugins.install.submitUninstall') as string}
        >
          <PackageMinus size={14} />
          <span>{uninstallBusy ? t('plugins.install.uninstalling') : t('plugins.install.submitUninstall')}</span>
        </button>
      </div>
    </section>
  )
}

interface DetailDialogProps {
  plugin: PluginInfo
  health?: PluginHealthResponse
  onClose: () => void
}

function DetailDialog({ plugin, health, onClose }: DetailDialogProps) {
  const { t } = useTranslation()
  const dialogRef = useRef<HTMLDivElement>(null)
  const sourceKey = ['entry_point', 'catalog', 'config_path'].includes(plugin.source)
    ? plugin.source
    : 'unknown'
  const statusKey = ['loaded', 'available', 'disabled', 'error'].includes(plugin.status)
    ? plugin.status
    : 'unknown'
  const healthEntries = useMemo(() => {
    if (!health) return []
    return Object.entries(health).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])
  }, [health])
  const titleId = useMemo(
    () => `souwen-plugin-detail-${plugin.name.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
    [plugin.name],
  )
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const first = getFocusableElements(dialogRef.current)[0] ?? dialogRef.current
    first?.focus()
    return () => previous?.focus()
  }, [])

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = getFocusableElements(dialogRef.current)
      if (focusable.length === 0) {
        event.preventDefault()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  return (
    <div className={styles.dialogBackdrop} onClick={onClose}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={styles.dialogHeader}>
          <h3 id={titleId}>
            <PlugZap size={16} />
            <span>{t('plugins.detail.title', { name: plugin.name })}</span>
          </h3>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={onClose}
            aria-label={t('plugins.detail.close') as string}
          >
            <X size={16} />
          </button>
        </header>
        <dl className={styles.dialogBody}>
          <dt>{t('plugins.detail.package')}</dt>
          <dd>{plugin.package || '—'}</dd>
          <dt>{t('plugins.detail.version')}</dt>
          <dd>{plugin.version || '—'}</dd>
          <dt>{t('plugins.detail.status')}</dt>
          <dd>{t(`plugins.status.${statusKey}`)}</dd>
          <dt>{t('plugins.detail.source')}</dt>
          <dd>{t(`plugins.source.${sourceKey}`)}</dd>
          <dt>{t('plugins.detail.firstParty')}</dt>
          <dd>{plugin.first_party ? <CheckCircle2 size={14} /> : t('plugins.detail.no')}</dd>
          <dt>{t('plugins.detail.description')}</dt>
          <dd>{plugin.description || '—'}</dd>
          <dt>{t('plugins.detail.adapters')}</dt>
          <dd>{plugin.source_adapters.length > 0 ? plugin.source_adapters.join(', ') : '—'}</dd>
          <dt>{t('plugins.detail.handlers')}</dt>
          <dd>{plugin.fetch_handlers.length > 0 ? plugin.fetch_handlers.join(', ') : '—'}</dd>
          {plugin.error ? (
            <>
              <dt>{t('plugins.detail.error')}</dt>
              <dd className={styles.errorText}>{plugin.error}</dd>
            </>
          ) : null}
          <dt>{t('plugins.detail.restartRequired')}</dt>
          <dd>{plugin.restart_required ? t('plugins.detail.yes') : t('plugins.detail.no')}</dd>
          <dt>{t('plugins.detail.lastHealth')}</dt>
          <dd>
            {healthEntries.length === 0 ? (
              t('plugins.detail.noHealth')
            ) : (
              <ul className={styles.healthList}>
                {healthEntries.map(([k, v]) => (
                  <li key={k}>
                    <code>{k}</code>: <span>{v}</span>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </dl>
        <footer className={styles.dialogFooter}>
          <button type="button" className={styles.actionBtn} onClick={onClose}>
            {t('plugins.detail.close')}
          </button>
        </footer>
      </div>
    </div>
  )
}

function getFocusableElements(root: HTMLElement | null): HTMLElement[] {
  if (!root) return []
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      [
        'a[href]',
        'button:not([disabled])',
        'input:not([disabled])',
        'select:not([disabled])',
        'textarea:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
      ].join(','),
    ),
  ).filter((element) => {
    const style = window.getComputedStyle(element)
    return style.display !== 'none' && style.visibility !== 'hidden'
  })
}
