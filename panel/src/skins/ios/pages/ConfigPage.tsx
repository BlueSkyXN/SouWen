/**
 * 文件用途：iOS 皮肤的配置页面，以分组形式展示和查看服务器配置参数
 *
 * 组件/函数清单：
 *   ConfigPage（函数组件）
 *     - 功能：获取服务器配置并按分组（基础、网络、搜索）分类展示
 *       1. 异步获取 ConfigResponse
 *       2. 按预定义的 CONFIG_SECTIONS 分组展示配置
 *       3. 每行配置项显示标签和值，支持特殊值的格式化展示（掩盖密码、JSON 对象、布尔值）
 *     - State 状态：config (ConfigResponse) 配置数据, loading/error 加载状态
 *     - 关键常量：BASIC_KEYS/NETWORK_KEYS/SEARCH_KEYS 配置项分类
 *     - 关键钩子：useTranslation 翻译, useNotificationStore 提示
 *
 *   ConfigRow（子组件）
 *     - 功能：单个配置项的显示组件，支持多种值类型的格式化
 *     - Props 属性：configKey 配置键, value 配置值, t 翻译函数
 *     - 逻辑：掩盖敏感字段（密码），显示 null/对象/布尔/字符串等
 *
 * 模块依赖：
 *   - react: 状态管理
 *   - react-i18next: 国际化翻译
 *   - framer-motion: 动画
 *   - lucide-react: 图标
 *   - @core/services/api: 获取配置
 *   - @core/stores/notificationStore: 提示消息
 *   - @core/lib/animations: 堆积容器动画配置
 *   - ConfigPage.module.scss: 样式
 */

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Settings, RefreshCw, Globe, Search, Wrench, CheckCircle2 } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { ConfigResponse } from '@core/types'
import styles from './ConfigPage.module.scss'

// 配置项分组定义
const BASIC_KEYS = ['api_password', 'log_level', 'max_workers', 'host', 'port', 'debug']
const NETWORK_KEYS = ['proxy', 'http_backend', 'timeout', 'concurrent_limit']
const SEARCH_KEYS = ['searxng_url', 'cache_enabled', 'cache_ttl']
const MASKED_KEYS = new Set(['api_password']) // 需要掩盖的敏感字段

interface SectionDef {
  id: string
  titleKey: string
  icon: React.ReactNode
  keys: string[]
}

const CONFIG_SECTIONS: SectionDef[] = [
  { id: 'basic', titleKey: 'config.sectionBasic', icon: <Settings size={14} />, keys: BASIC_KEYS },
  { id: 'network', titleKey: 'config.sectionNetwork', icon: <Globe size={14} />, keys: NETWORK_KEYS },
  { id: 'search', titleKey: 'config.sectionSearch', icon: <Search size={14} />, keys: SEARCH_KEYS },
]

type TFunc = ReturnType<typeof useTranslation>['t']

// 获取配置项的本地化标签
function getConfigLabel(key: string, t: TFunc): string {
  return t(`config.labels.${key}`, { defaultValue: key })
}

// 单个配置行组件 - 展示配置项的标签和值
function ConfigRow({ configKey, value, t }: { configKey: string; value: unknown; t: TFunc }) {
  const label = getConfigLabel(configKey, t)
  const isMasked = value === '***' || MASKED_KEYS.has(configKey)
  const isNull = value === null || value === undefined

  return (
    <div className={styles.configRow}>
      <div className={styles.configLabel}>{label}</div>
      <div className={styles.configValue}>
        {isMasked && value === '***' ? (
          <span className={styles.maskedBadge}>
            <CheckCircle2 size={12} />
            {t('config.configured')}
          </span>
        ) : isNull ? (
          <span className={styles.nullVal}>{t('config.notSet')}</span>
        ) : typeof value === 'object' ? (
          <code className={styles.codeVal}>{JSON.stringify(value)}</code>
        ) : typeof value === 'boolean' ? (
          <span className={`${styles.boolBadge} ${value ? styles.boolTrue : styles.boolFalse}`}>
            {String(value)}
          </span>
        ) : (
          <span className={styles.plainVal}>{String(value)}</span>
        )}
      </div>
    </div>
  )
}

// ConfigPage 组件 - 配置展示页面
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

    const advanced = entries
      .filter(([key]) => !categorized.has(key))
      .map(([key, value]) => ({ key, value }))

    return { sections: secs, advancedEntries: advanced }
  }, [config])

  if (loading) {
    return <Spinner label={t('common.loading', 'Loading...')} />
  }

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      {/* ── Header ── */}
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>
            <Settings size={20} />
            {t('config.title', 'Configuration')}
          </h1>
          <p className={styles.pageDesc}>{t('config.note')}</p>
        </div>
        <button
          className={styles.commitBtn}
          onClick={handleReload}
          disabled={reloading}
        >
          <RefreshCw size={14} />
          {reloading ? t('config.reloading') : t('config.reload', 'Reload Configuration')}
        </button>
      </m.div>

      {/* ── Config Sections ── */}
      {sections.map((section) => (
        <m.div key={section.id} className={styles.configSection} variants={staggerItem}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>{section.icon}</span>
            {t(section.titleKey, section.titleKey)}
          </div>
          {section.items.map(({ key, value }) => (
            <ConfigRow key={key} configKey={key} value={value} t={t} />
          ))}
        </m.div>
      ))}

      {/* ── Advanced / Credentials ── */}
      {advancedEntries.length > 0 && (
        <m.div className={styles.configSection} variants={staggerItem}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}><Wrench size={14} /></span>
            {t('config.sectionCredentials', 'Credentials & Keys')}
          </div>
          {advancedEntries.map(({ key, value }) => (
            <ConfigRow key={key} configKey={key} value={value} t={t} />
          ))}
        </m.div>
      )}
    </m.div>
  )
}
