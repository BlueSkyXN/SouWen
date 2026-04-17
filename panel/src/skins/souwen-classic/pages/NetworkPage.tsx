/**
 * 网络配置页面 - HTTP 后端和抓取引擎管理
 *
 * 文件用途：显示和配置网络相关设置，包括 HTTP 后端选择（curl_cffi/httpx）和爬虫引擎配置
 *
 * 核心模块：
 *   - HttpBackendCard：配置 HTTP 后端及各数据源的后端覆盖
 *   - ScraperEngineCard：配置搜索爬虫引擎选择
 *
 * 功能特性：
 *   - 检测 curl_cffi 可用性（显示安装状态徽章）
 *   - 后端选择：auto / curl_cffi / httpx
 *   - 按源覆盖：为特定数据源指定不同的后端
 *   - 爬虫引擎选择：10 种搜索引擎可选
 *   - 实时更新反馈（toast 提示）
 *   - 加载和错误处理
 *
 * 主要交互：
 *   - 页面加载时获取网络配置
 *   - 下拉选择后端类型自动保存
 *   - 刷新按钮重新加载配置
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Info, Shield, ShieldOff, Plug,
  Settings, Globe, HelpCircle,
  CircleDot, Wifi,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { Card } from '../components/common/Card'
import { Tooltip } from '../components/common/Tooltip'
import { Input } from '../components/common/Input'
import { Button } from '../components/common/Button'
import { Badge } from '../components/common/Badge'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import type { WarpStatus, HttpBackendResponse } from '@core/types'
import styles from './NetworkPage.module.scss'

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

export function NetworkPage() {
  const { t } = useTranslation()

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>{t('network.pageTitle')}</h1>
          <p className={styles.pageDesc}>{t('network.pageSubtitle')}</p>
        </div>
      </m.div>

      <m.div variants={staggerItem}>
        <WarpCard />
      </m.div>

      <m.div variants={staggerItem}>
        <HttpBackendCard />
      </m.div>
    </m.div>
  )
}
