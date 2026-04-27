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
  Info, Shield, Plug, HelpCircle,
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

/** 可选的搜索爬虫引擎列表（用于 ScraperEngineCard 下拉选项） */
const SCRAPER_ENGINES = [
  'duckduckgo', 'yahoo', 'brave', 'google', 'bing',
  'startpage', 'baidu', 'mojeek', 'yandex', 'google_patents',
]

/** HTTP 后端可选项：auto 自动选择 / curl_cffi 浏览器指纹 / httpx 标准客户端 */
const BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const

/**
 * HttpBackendCard 组件：HTTP 后端配置卡片
 * 功能：展示当前后端、curl_cffi 安装状态，允许设置默认后端及为单个数据源覆盖后端
 */
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

/**
 * WarpSummaryCard 组件：WARP 状态摘要，引导用户进入专属管理页面
 */
function WarpSummaryCard() {
  const { t } = useTranslation()
  const [warp, setWarp] = useState<WarpStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getWarpStatus().then(setWarp).catch(() => null).finally(() => setLoading(false))
  }, [])

  if (loading) return null

  const statusColor = warp?.status === 'enabled' ? 'green' : warp?.status === 'error' ? 'red' : 'gray'

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>
          <Shield size={18} />
          {t('warp.title')}
        </div>
        {warp && <Badge color={statusColor}>{t(`warp.${warp.status}`)}</Badge>}
      </div>
      {warp && warp.status !== 'disabled' && (
        <div className={styles.warpGrid}>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>{t('warp.mode')}</div>
            <div className={styles.fieldValue}>{warp.mode}</div>
          </div>
          <div className={styles.warpField}>
            <div className={styles.fieldLabel}>{t('warp.ip')}</div>
            <div className={styles.fieldValue}>{warp.ip || '—'}</div>
          </div>
        </div>
      )}
      <div style={{ marginTop: '12px' }}>
        <a href="/warp" style={{ color: 'var(--primary)', textDecoration: 'none', fontSize: '14px' }}>
          → {t('warp.pageTitle')}
        </a>
      </div>
    </Card>
  )
}

/**
 * ProxyConfigCard 组件：全局代理配置卡片
 * 功能：管理全局 HTTP/SOCKS 代理与代理池，显示 socksio 安装状态
 */
function ProxyConfigCard() {
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

  if (loading) return null

  return (
    <Card className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}>
          <Shield size={18} />
          {t('proxy.title')}
        </div>
        <Badge color={socksSupported ? 'green' : 'amber'}>
          {socksSupported ? t('proxy.socksAvailable') : t('proxy.socksUnavailable')}
        </Badge>
      </div>

      <div className={styles.infoNote}>
        <Info size={14} />
        <span>{t('proxy.description')}</span>
      </div>

      <div className={styles.proxyField}>
        <label className={styles.proxyLabel}>{t('proxy.globalProxy')}</label>
        <Input
          value={proxy}
          onChange={(e) => setProxy(e.target.value)}
          placeholder={t('proxy.globalProxyPlaceholder')}
        />
      </div>

      <div className={styles.proxyField}>
        <label className={styles.proxyLabel}>{t('proxy.proxyPool')}</label>
        <p className={styles.proxyHint}>{t('proxy.poolDescription')}</p>
        <textarea
          className={styles.proxyTextarea}
          value={poolText}
          onChange={(e) => setPoolText(e.target.value)}
          placeholder={t('proxy.proxyPoolPlaceholder')}
          rows={3}
        />
      </div>

      <div className={styles.proxyActions}>
        <Button variant="primary" size="sm" loading={saving} onClick={handleSave}>
          {saving ? t('proxy.saving') : t('proxy.save')}
        </Button>
        <Button variant="ghost" size="sm" disabled={saving} onClick={handleClear}>
          {t('proxy.clear')}
        </Button>
      </div>
    </Card>
  )
}

/**
 * NetworkPage 主组件
 * 组合 WARP 摘要、ProxyConfigCard 与 HttpBackendCard，提供网络层配置入口
 */
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
        <WarpSummaryCard />
      </m.div>

      <m.div variants={staggerItem}>
        <ProxyConfigCard />
      </m.div>

      <m.div variants={staggerItem}>
        <HttpBackendCard />
      </m.div>
    </m.div>
  )
}
