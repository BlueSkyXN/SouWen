/**
 * 文件用途：iOS 皮肤的仪表板页面，展示系统健康状态、数据源统计和健康检查结果
 *
 * 组件/函数清单：
 *   DashboardPage（函数组件）
 *     - 功能：首页仪表板，异步获取系统诊断数据（DoctorResponse），展示：
 *       1. Hero 区域：健康状态标题和描述
 *       2. 核心指标：论文来源数、专利来源数、网页来源数、可用数据源比例
 *       3. 健康表格：详细列表显示每个数据源的状态、名称、类型、层级等
 *     - State 状态：doctor (DoctorResponse | null) 诊断数据, loading (bool) 加载中, fetchError (bool) 获取失败
 *     - 关键钩子：useTranslation 获取翻译, useNotificationStore 显示提示, useAuthStore 版本号
 *     - 关键计算：paperCount/patentCount/webCount 按类别统计数据源数量, healthPct 健康百分比
 *     - 错误处理：加载失败时显示错误状态卡和重试按钮
 *
 * 模块依赖：
 *   - react-i18next: 国际化翻译
 *   - lucide-react: 图标
 *   - @core/services/api: api.getDoctor 获取诊断数据
 *   - @core/stores: notificationStore 提示, authStore 版本号
 *   - @core/lib/errors: formatError 错误格式化
 *   - ./components/common/Spinner: 加载旋转圈
 *   - DashboardPage.module.scss: 页面样式
 */

import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Activity, FileText, Shield, Globe, RefreshCw, ChevronRight } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { useAuthStore } from '@core/stores/authStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse } from '@core/types'
import styles from './DashboardPage.module.scss'

// DashboardPage 组件 - 系统仪表板
export function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const version = useAuthStore((s) => s.version)
  const addToast = useNotificationStore((s) => s.addToast)

  // 从服务器获取诊断数据（数据源状态、统计、配置信息）
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

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  if (loading) {
    return <Spinner label={t('common.loading', 'Loading...')} />
  }

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
      <h1 className={styles.pageTitle}>{t('dashboard.title', '仪表盘')}</h1>

      {/* ── Stat Cards ── */}
      <m.div
        className={styles.statsGrid}
        variants={staggerContainer}
        initial="initial"
        animate="animate"
      >
        <m.div variants={staggerItem} className={`${styles.statCard} ${styles.clickable}`} onClick={() => navigate('/search/paper')} role="link" tabIndex={0} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/paper')}>
          <span className={styles.statIcon} style={{ background: '#007aff' }}>
            <FileText size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{paperCount}</div>
            <div className={styles.statLabel}>{t('dashboard.paperSources')}</div>
          </div>
          <ChevronRight size={18} className={styles.statChevron} />
        </m.div>

        <m.div variants={staggerItem} className={`${styles.statCard} ${styles.clickable}`} onClick={() => navigate('/search/patent')} role="link" tabIndex={0} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/patent')}>
          <span className={styles.statIcon} style={{ background: '#ff9500' }}>
            <Shield size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{patentCount}</div>
            <div className={styles.statLabel}>{t('dashboard.patentSources')}</div>
          </div>
          <ChevronRight size={18} className={styles.statChevron} />
        </m.div>

        <m.div variants={staggerItem} className={`${styles.statCard} ${styles.clickable}`} onClick={() => navigate('/search/web')} role="link" tabIndex={0} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/search/web')}>
          <span className={styles.statIcon} style={{ background: '#34c759' }}>
            <Globe size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>{webCount}</div>
            <div className={styles.statLabel}>{t('dashboard.webEngines')}</div>
          </div>
          <ChevronRight size={18} className={styles.statChevron} />
        </m.div>

        <m.div variants={staggerItem} className={`${styles.statCard} ${styles.clickable}`} onClick={() => navigate('/sources')} role="link" tabIndex={0} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && navigate('/sources')}>
          <span className={styles.statIcon} style={{ background: '#5856d6' }}>
            <Activity size={18} color="#fff" />
          </span>
          <div className={styles.statInfo}>
            <div className={styles.statValue}>
              {okCount}<span className={styles.statFraction}>/{totalCount}</span>
            </div>
            <div className={styles.statLabel}>{t('dashboard.availableSources')}</div>
          </div>
          <ChevronRight size={18} className={styles.statChevron} />
        </m.div>
      </m.div>

      {/* ── Health Status ── */}
      <div className={styles.formGroup}>
        <div className={styles.groupTitle}>{t('dashboard.sourceHealth')}</div>
        <div className={styles.groupCard}>
          {/* Summary row */}
          <div className={styles.formRow}>
            <span className={styles.rowLabel}>{t('dashboard.health', 'Health')}</span>
            <span className={styles.rowValue}>
              <span className={`${styles.statusDot} ${healthPct > 50 ? styles.statusOk : styles.statusErr}`} />
              {healthPct}% — {healthPct > 50 ? t('dashboard.statusOk', 'Healthy') : t('dashboard.statusDegraded', 'Degraded')}
            </span>
          </div>
          {version && (
            <div className={styles.formRow}>
              <span className={styles.rowLabel}>{t('dashboard.version', 'Version')}</span>
              <span className={styles.rowValueMuted}>v{version}</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Source List ── */}
      <div className={styles.formGroup}>
        <div className={styles.groupTitle}>{t('dashboard.name', 'Sources')}</div>
        <div className={styles.groupCard}>
          {sortedSources.map((src, i) => {
            const statusClass = src.status === 'ok'
              ? styles.statusOk
              : src.status === 'needs_key'
                ? styles.statusWarn
                : styles.statusErr

            return (
              <div key={src.name} className={`${styles.formRow} ${i < sortedSources.length - 1 ? styles.formRowSep : ''}`}>
                <div className={styles.sourceInfo}>
                  <span className={`${styles.statusDot} ${statusClass}`} />
                  <span className={styles.sourceName}>{src.name}</span>
                  <span className={styles.typeBadge}>{src.category}</span>
                </div>
                <span className={styles.rowValueMuted}>{src.integration_type === 'open_api' ? '开放' : src.integration_type === 'scraper' ? '爬虫' : src.integration_type === 'official_api' ? '授权' : '自建'}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
