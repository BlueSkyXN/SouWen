/**
 * 配置页面 - 应用配置查看和管理
 *
 * 文件用途：显示应用服务端配置项（API 密码、日志级别、超时、缓存等），
 * 分类展示为基础/网络/搜索三个可折叠面板
 *
 * 常量定义：
 *   BASIC_KEYS - 基础配置项键名
 *   NETWORK_KEYS - 网络配置项键名  
 *   SEARCH_KEYS - 搜索配置项键名
 *   MASKED_KEYS - 敏感字段（显示为 *** 掩码）
 *   CONFIG_SECTIONS - 配置面板元数据（图标、i18n 键等）
 *
 * 功能模块：
 *   - 配置项分类显示
 *   - 敏感数据掩码
 *   - 值格式化（code block、null 提示等）
 *   - 可折叠手风琴布局
 *   - 加载中骨架屏
 *   - 错误处理和重试
 *
 * 页面交互：
 *   - 页面加载时从 API 获取配置
 *   - 刷新按钮重新加载配置
 *   - 点击手风琴展开/收缩配置段
 *   - Tooltip 显示配置项详细说明
 */

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  RefreshCw,
  Settings, Globe, Search, Wrench, HelpCircle, CheckCircle2,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { Accordion } from '../components/common/Accordion'
import { Tooltip } from '../components/common/Tooltip'
import { Button } from '../components/common/Button'
import { Badge } from '../components/common/Badge'
import { TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import type { ConfigResponse } from '@core/types'
import styles from './ConfigPage.module.scss'

// 基础配置键名
const BASIC_KEYS = ['api_password', 'log_level', 'max_workers', 'host', 'port', 'debug']
// 网络配置键名
const NETWORK_KEYS = ['proxy', 'http_backend', 'timeout', 'concurrent_limit']
// 搜索配置键名
const SEARCH_KEYS = ['searxng_url', 'cache_enabled', 'cache_ttl']
// 敏感字段集合（显示为 *** 掩码）
const MASKED_KEYS = new Set(['api_password'])

interface ConfigSection {
  id: string
  titleKey: string
  descKey: string
  icon: React.ReactNode
  keys: string[]
}

// 配置分组定义
const CONFIG_SECTIONS: ConfigSection[] = [
  { id: 'basic', titleKey: 'config.sectionBasic', descKey: 'config.sectionBasicDesc', icon: <Settings size={16} />, keys: BASIC_KEYS },
  { id: 'network', titleKey: 'config.sectionNetwork', descKey: 'config.sectionNetworkDesc', icon: <Globe size={16} />, keys: NETWORK_KEYS },
  { id: 'search', titleKey: 'config.sectionSearch', descKey: 'config.sectionSearchDesc', icon: <Search size={16} />, keys: SEARCH_KEYS },
]

type TFunc = ReturnType<typeof useTranslation>['t']

/**
 * 获取配置项的 i18n 标签
 * @param key - 配置键名
 * @param t - i18n 翻译函数
 * @returns 翻译后的标签或原始键名
 */
function getConfigLabel(key: string, t: TFunc): string {
  return t(`config.labels.${key}`, { defaultValue: key })
}

/**
 * 获取配置项的描述/说明文本
 * @param key - 配置键名
 * @param t - i18n 翻译函数
 * @returns 描述文本或 undefined
 */
function getConfigDescription(key: string, t: TFunc): string | undefined {
  const desc = t(`config.descriptions.${key}`, { defaultValue: '' })
  return desc || undefined
}

/**
 * 单个配置行显示组件
 * 
 * 显示配置项名称、值、说明提示和错误状态
 */
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

    </m.div>
  )
}
