/**
 * 文件用途：Apple 皮肤的仪表板页面，展示系统健康状态、数据源统计和健康检查结果
 *
 * 组件/函数清单：
 *   DashboardPage（函数组件）
 *     - 功能：首页仪表板，异步获取系统诊断数据（DoctorResponse），展示：
 *       1. Hero 区域：健康状态标题和描述
 *       2. 核心指标：论文来源数、专利来源数、可用数据源比例
 *       3. 健康表格：详细列表显示每个数据源的状态、名称、类型、层级、所需密钥、诊断信息
 *     - State 状态：doctor (DoctorResponse | null) 诊断数据, loading (bool) 加载中, fetchError (bool) 获取失败
 *     - 关键钩子：useTranslation 获取翻译, useNotificationStore 显示提示
 *     - 关键计算：paperCount 论文来源数, patentCount 专利来源数, healthPct 健康百分比 (ok/total)
 *     - 错误处理：加载失败时显示错误状态卡和重试按钮
 *
 * 模块依赖：
 *   - react-i18next: 国际化翻译
 *   - lucide-react: RefreshCw 刷新图标
 *   - @core/services/api: api.getDoctor 获取诊断数据
 *   - @core/stores/notificationStore: 消息提示
 *   - @core/lib/errors: formatError 错误格式化
 *   - ./components/common/Spinner: 加载旋转圈
 *   - DashboardPage.module.scss: 页面样式
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse } from '@core/types'
import styles from './DashboardPage.module.scss'

/**
 * DashboardPage 组件 - 系统仪表板
 * 展示数据源健康状态、核心指标和诊断信息
 */
export function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const addToast = useNotificationStore((s) => s.addToast)

  /**
   * 从服务器获取诊断数据（数据源状态、统计、配置信息）
   */
  const fetchData = useCallback(async () => {
    setLoading(true)
    setFetchError(false)
    try {
      const d = await api.getDoctor()
      setDoctor(d)
    } catch (err) {
      setFetchError(true)
      addToast('error', t('dashboard.fetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  // 页面首次加载时获取数据
  useEffect(() => {
    void fetchData()
  }, [fetchData])

  // 加载中状态：显示加载旋转圈
  if (loading) {
    return <Spinner label={t('common.loading', 'Loading...')} />
  }

  // 加载失败状态：显示错误消息和重试按钮
  if (fetchError || !doctor) {
    return (
      <div className={styles.errorState}>
        <p>{t('dashboard.fetchFailed', { message: '' })}</p>
        <button className={styles.retryBtn} onClick={fetchData}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          {t('sources.refresh')}
        </button>
      </div>
    )
  }

  // 从诊断数据中提取统计信息
  const paperCount = doctor.sources.filter((s) => s.category === 'paper').length
  const patentCount = doctor.sources.filter((s) => s.category === 'patent').length
  const webCount = doctor.sources.filter((s) => !['paper', 'patent'].includes(s.category)).length
  const okCount = doctor.ok
  const totalCount = doctor.total
  const healthPct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  const statusOrder: Record<string, number> = { ok: 0, degraded: 1, needs_key: 2, error: 3, timeout: 4 }
  const sortedSources = [...doctor.sources].sort((a, b) => {
    const diff = (statusOrder[a.status] ?? 5) - (statusOrder[b.status] ?? 5)
    return diff !== 0 ? diff : a.name.localeCompare(b.name)
  })

  return (
    <div className={styles.page}>
      {/* ── Hero Section 英雄区：标题、描述和核心指标 ── */}
      <div className={styles.heroSection}>
        <div className={styles.heroSubtitle}>SouWen {t('dashboard.title', 'Dashboard')}</div>
        <h1 className={styles.heroTitle}>
          {/* 根据系统健康状态显示不同的标题 */}
          {healthPct > 50
            ? t('dashboard.heroHealthy', '掌控全局，就是这么简单。')
            : t('dashboard.heroDegraded', '部分服务降级，请检查配置。')}
        </h1>
        <p className={styles.heroDesc}>
          {t('dashboard.heroDesc', '核心指标一目了然。无论是论文数据库的实时状态，还是专利接口的探测情况，尽在掌握。')}
        </p>

        {/* ── Giant Metric Numbers 巨大的核心指标卡 ── */}
        <div className={styles.metricsRow}>
          <div
            className={`${styles.metricItem} ${styles.clickable}`}
            onClick={() => navigate('/search/paper')}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/paper')}
          >
            <div className={styles.metricLabel}>{t('dashboard.paperSources')}</div>
            <div className={styles.metricValue}>{paperCount}</div>
            <div className={styles.metricDesc}>{t('dashboard.ready', '就绪')}</div>
          </div>
          <div
            className={`${styles.metricItem} ${styles.clickable}`}
            onClick={() => navigate('/search/patent')}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/patent')}
          >
            <div className={styles.metricLabel}>{t('dashboard.patentSources')}</div>
            <div className={styles.metricValue}>{patentCount}</div>
            <div className={styles.metricDesc}>{t('dashboard.ready', '就绪')}</div>
          </div>
          <div
            className={`${styles.metricItem} ${styles.clickable}`}
            onClick={() => navigate('/search/web')}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/web')}
          >
            <div className={styles.metricLabel}>{t('dashboard.webEngines')}</div>
            <div className={styles.metricValue}>{webCount}</div>
            <div className={styles.metricDesc}>{t('dashboard.ready', '就绪')}</div>
          </div>
          <div
            className={`${styles.metricItem} ${styles.clickable}`}
            onClick={() => navigate('/sources')}
            role="link"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/sources')}
          >
            <div className={styles.metricLabel}>{t('dashboard.availableSources')}</div>
            <div className={styles.metricValue}>
              {okCount}<span className={styles.metricFraction}>/{totalCount}</span>
            </div>
            {/* 健康状态徽章，健康情况 <= 50% 时显示警告样式 */}
            <div className={`${styles.metricDesc} ${healthPct <= 50 ? styles.metricDescAlert : ''}`}>
              {healthPct > 50
                ? t('dashboard.statusOk', 'Healthy')
                : t('dashboard.statusDegraded', 'Degraded')}
            </div>
          </div>
        </div>
      </div>

      {/* ── Health Table 数据源健康详情表 ── */}
      <div className={styles.tableSection}>
        <h3 className={styles.sectionTitle}>{t('dashboard.sourceHealth')}</h3>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t('dashboard.status')}</th>
                <th>{t('dashboard.name', 'Name')}</th>
                <th>{t('dashboard.type')}</th>
                <th>{t('dashboard.tier')}</th>
                <th>{t('dashboard.requiredKey')}</th>
                <th>{t('dashboard.diagnostics', 'Details')}</th>
              </tr>
            </thead>
            <tbody>
              {sortedSources.map((src) => {
                const statusClass = src.status === 'ok'
                  ? styles.statusOk
                  : src.status === 'needs_key'
                    ? styles.statusWarn
                    : styles.statusErr
                const statusLabel = src.status === 'ok'
                  ? t('dashboard.ok', 'OK')
                  : src.status === 'needs_key'
                    ? t('dashboard.needsKey', 'Needs Key')
                    : t('dashboard.error', 'Error')

                return (
                  <tr key={src.name}>
                    <td>
                      <span className={`${styles.statusIndicator} ${statusClass}`}>
                        <span className={styles.statusDot} />
                        {statusLabel}
                      </span>
                    </td>
                    <td className={styles.nodeName}>{src.name}</td>
                    <td>
                      <span className={`${styles.typeBadge} ${styles[src.category]}`}>
                        {src.category}
                      </span>
                    </td>
                    <td>
                      <span className={styles.tierBadge}>{src.integration_type === 'open_api' ? '开放' : src.integration_type === 'scraper' ? '爬虫' : src.integration_type === 'official_api' ? '授权' : '自建'}</span>
                    </td>
                    <td>
                      <code className={styles.keyCode}>{src.required_key ?? '—'}</code>
                    </td>
                    <td className={styles.diagMessage}>{src.message}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
