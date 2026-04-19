/**
 * 控制面板页面 - 应用系统概览
 *
 * 文件用途：实时展示系统健康状态，包括服务健康度环图、统计卡片、数据源状态和健康监测详情
 *
 * 核心功能：
 *   - 健康度环图：动画显示系统健康百分比（颜色梯度：绿→黄→红）
 *   - 统计指标卡片：源数量、资源数、最后更新时间等
 *   - 数据源概览：按类别（paper/patent/web）分组展示源状态
 *   - 健康监测表：详细列表展示各数据源的状态、错误信息
 *
 * 常量：
 *   RING_SIZE / RING_STROKE / RING_CIRCUMFERENCE - SVG 环图参数
 *
 * 主要交互：
 *   - 页面加载时获取系统诊断数据
 *   - 刷新按钮重新加载数据
 *   - 环图和卡片显示动画
 *   - 加载中显示骨架屏
 *   - 错误时显示提示和重试选项
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { FileText, Shield, Globe, Layers, RefreshCw } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { useAuthStore } from '@core/stores/authStore'
import { Card } from '../components/common/Card'
import { Badge } from '../components/common/Badge'
import { EmptyState } from '../components/common/EmptyState'
import { StatsGridSkeleton, TableSkeleton } from '../components/common/Skeleton'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { categoryBadgeColor, integrationBadgeColor, categoryLabel } from '@core/lib/ui'
import type { DoctorResponse } from '@core/types'
import styles from './DashboardPage.module.scss'

/* ── Animated health ring (gradient stroke, animated on mount) ── */
const RING_SIZE = 160
const RING_STROKE = 10
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS

/**
 * HealthRing 组件：动画化的圆环健康度可视化
 * Props: pct 健康度百分比 (0-100)
 * 关键逻辑：
 *   - 渐变色根据百分比阈值切换：≥60 绿/青、≥30 橙、否则红
 *   - 挂载时通过 stroke-dasharray 从 0 动画过渡到目标值，实现"环图填充动画"
 */
function HealthRing({ pct }: { pct: number }) {
  const { t } = useTranslation()
  const strokeRef = useRef<SVGCircleElement>(null)
  const gradientId = 'health-grad'
  const filled = (pct / 100) * RING_CIRCUMFERENCE

  useEffect(() => {
    const el = strokeRef.current
    if (!el) return
    // start from 0 and animate to target
    el.style.transition = 'none'
    el.setAttribute('stroke-dasharray', `0 ${RING_CIRCUMFERENCE}`)
    // force reflow
    void el.getBoundingClientRect()
    el.style.transition = 'stroke-dasharray 1s cubic-bezier(.4,0,.2,1)'
    el.setAttribute('stroke-dasharray', `${filled} ${RING_CIRCUMFERENCE - filled}`)
  }, [filled])

  return (
    <div className={styles.healthRingWrap}>
      <svg
        width={RING_SIZE}
        height={RING_SIZE}
        viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
        role="img"
        aria-label={`${t('dashboard.healthRate')}: ${pct}%`}
        className={styles.healthRingSvg}
      >
        <title>{t('dashboard.healthRate')}: {pct}%</title>
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            {pct >= 60 ? (
              <>
                <stop offset="0%" stopColor="var(--accent-teal)" />
                <stop offset="100%" stopColor="var(--success)" />
              </>
            ) : pct >= 30 ? (
              <>
                <stop offset="0%" stopColor="var(--warning)" />
                <stop offset="100%" stopColor="#f59e0b" />
              </>
            ) : (
              <>
                <stop offset="0%" stopColor="var(--warning)" />
                <stop offset="100%" stopColor="var(--error)" />
              </>
            )}
          </linearGradient>
        </defs>
        {/* track */}
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke="var(--border)"
          strokeWidth={RING_STROKE}
        />
        {/* filled arc */}
        <circle
          ref={strokeRef}
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={RING_STROKE}
          strokeDasharray={`0 ${RING_CIRCUMFERENCE}`}
          strokeDashoffset={RING_CIRCUMFERENCE / 4}
          strokeLinecap="round"
          className={styles.healthStroke}
        />
      </svg>
      <div className={styles.healthValue}>
        <span className={styles.healthPct}>{pct}%</span>
        <span className={styles.healthLabel}>{t('dashboard.healthRate')}</span>
      </div>
    </div>
  )
}

/* ── Source matrix view ── */
type SourceLike = DoctorResponse['sources'][number]

/** 根据数据源状态返回对应的 CSS 类（绿点/红点/黄点） */
function matrixDotClass(status: string): string {
  if (status === 'ok') return styles.matrixDotOk
  if (status === 'error' || status === 'timeout') return styles.matrixDotErr
  return styles.matrixDotWarn
}

/** 根据数据源集成类型返回对应的 CSS 类 */
function matrixIntegrationClass(integration_type: string): string {
  if (integration_type === 'open_api') return styles.matrixTierT0
  if (integration_type === 'official_api') return styles.matrixTierT1
  return styles.matrixTierT2
}

/**
 * SourceMatrix 组件：以矩阵视图展示所有数据源
 * 按分类分组显示，每个芯片包含状态点 + 名称 + 集成类型标签
 */
function SourceMatrix({ sources }: { sources: SourceLike[] }) {
  const { t } = useTranslation()
  const order: Array<'paper' | 'patent' | 'web'> = ['paper', 'patent', 'web']
  const grouped = order
    .map((cat) => ({ cat, items: sources.filter((s) => s.category === cat) }))
    .filter((g) => g.items.length > 0)

  return (
    <Card className={styles.matrixCard}>
      <div className={styles.matrixHeader}>
        <div>
          <h3 className={styles.matrixTitle}>
            <span className={styles.matrixCount}>{sources.length}</span>
            {t('dashboard.sourceMatrix')}
          </h3>
          <p className={styles.matrixSubtitle}>{t('dashboard.sourceMatrixDesc')}</p>
        </div>
        <span className={styles.matrixToggle}>MATRIX VIEW</span>
      </div>
      <div className={styles.matrixGroups}>
        {grouped.map((group, idx) => (
          <div
            key={group.cat}
            className={`${styles.matrixGroup} ${idx > 0 ? styles.matrixGroupDivided : ''}`}
          >
            <div className={styles.matrixGroupLabel}>
              <span className={styles.matrixGroupName}>{categoryLabel(t, group.cat)}</span>
              <span className={styles.matrixGroupCount}>{group.items.length}</span>
            </div>
            <div className={styles.matrixChips}>
              {group.items.map((src) => (
                <span key={src.name} className={styles.matrixChip} title={src.message}>
                  <span className={`${styles.matrixDot} ${matrixDotClass(src.status)}`} />
                  <span className={styles.matrixChipName}>{src.name}</span>
                  <span className={`${styles.matrixTier} ${matrixIntegrationClass(src.integration_type)}`}>
                    {src.integration_type === 'open_api' ? '开放' : src.integration_type === 'scraper' ? '爬虫' : src.integration_type === 'official_api' ? '授权' : '自建'}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ── Availability progress bar ── */
/** AvailabilityBar 组件：可用性进度条，显示 ok/total 数据源比例 */
function AvailabilityBar({ ok, total }: { ok: number; total: number }) {
  const pct = total > 0 ? (ok / total) * 100 : 0
  return (
    <div className={styles.availBar}>
      <div className={styles.availTrack}>
        <div className={styles.availFill} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.availText}>{ok}/{total}</span>
    </div>
  )
}

/**
 * DashboardPage 主组件
 * 状态：doctor 系统诊断数据、loading 加载标志、fetchError 错误标志、lastUpdated 上次刷新时间
 * 流程：挂载时调用 api.getDoctor() 获取健康数据；失败时展示错误提示并允许重试
 */
export function DashboardPage() {
  const { t } = useTranslation()
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const version = useAuthStore((s) => s.version)
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setFetchError(false)
    try {
      const d = await api.getDoctor()
      setDoctor(d)
      setLastUpdated(new Date())
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

  /* ── Loading ── */
  if (loading) return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      <span className="srOnly">{t('common.loading', 'Loading dashboard data')}</span>
      <Card className={styles.headerCard}>
        <div className={styles.headerSkeleton}>
          <div className={styles.skeletonLine} style={{ width: '30%' }} />
          <div className={styles.skeletonLine} style={{ width: '20%' }} />
        </div>
      </Card>
      <StatsGridSkeleton count={5} />
      <TableSkeleton rows={6} cols={4} />
    </div>
  )

  /* ── Error ── */
  if (fetchError || !doctor) {
    return (
      <div className={styles.page}>
        <EmptyState
          type="error"
          title={t('common.error')}
          description={t('dashboard.fetchFailed', { message: '' })}
          action={
            <button className="btn btn-primary btn-sm" onClick={fetchData}>
              <RefreshCw size={14} />
              {t('sources.refresh')}
            </button>
          }
        />
      </div>
    )
  }

  const paperCount = doctor.sources.filter((s) => s.category === 'paper').length
  const patentCount = doctor.sources.filter((s) => s.category === 'patent').length
  const webCount = doctor.sources.filter((s) => s.category === 'web').length
  const okCount = doctor.ok
  const totalCount = doctor.total
  const healthPct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  return (
    <div className={styles.page}>
      {/* ── Page title ── */}
      <div className={styles.pageTitle}>
        <h1 className={styles.pageTitleText}>{t('dashboard.pageTitle')}</h1>
        <p className={styles.pageSubtitle}>{t('dashboard.pageSubtitle')}</p>
      </div>

      {/* ── Header ── */}
      <Card className={styles.headerCard}>
        <div className={styles.headerRow}>
          <div className={styles.headerLeft}>
            <div className={styles.statusChip}>
              <span className={styles.statusDot} />
              <span className={styles.statusText}>{t('dashboard.running')}</span>
            </div>
            <Badge color="gray">{version || '—'}</Badge>
          </div>
          <div className={styles.headerRight}>
            <span className={styles.headerLabel}>{t('dashboard.availableSources')}</span>
            <AvailabilityBar ok={okCount} total={totalCount} />
          </div>
        </div>
      </Card>

      {/* ── Stats + Health ring ── */}
      <m.div className={styles.statsSection} variants={staggerContainer} initial="initial" animate="animate">
        <div className={styles.statsGrid}>
          <m.div variants={staggerItem} className={`${styles.statCard} ${styles.statBlue}`}>
            <div className={styles.statBlob} />
            <div className={styles.statHeader}>
              <div className={`${styles.statIcon} ${styles.iconBlue}`}><FileText size={18} /></div>
            </div>
            <div className={`${styles.statValue} ${styles.valueBlue}`}>{paperCount}</div>
            <span className={styles.statTitle}>{t('dashboard.paperSources')}</span>
          </m.div>

          <m.div variants={staggerItem} className={`${styles.statCard} ${styles.statAmber}`}>
            <div className={styles.statBlob} />
            <div className={styles.statHeader}>
              <div className={`${styles.statIcon} ${styles.iconAmber}`}><Shield size={18} /></div>
            </div>
            <div className={`${styles.statValue} ${styles.valueAmber}`}>{patentCount}</div>
            <span className={styles.statTitle}>{t('dashboard.patentSources')}</span>
          </m.div>

          <m.div variants={staggerItem} className={`${styles.statCard} ${styles.statGreen}`}>
            <div className={styles.statBlob} />
            <div className={styles.statHeader}>
              <div className={`${styles.statIcon} ${styles.iconGreen}`}><Globe size={18} /></div>
            </div>
            <div className={`${styles.statValue} ${styles.valueGreen}`}>{webCount}</div>
            <span className={styles.statTitle}>{t('dashboard.webEngines')}</span>
          </m.div>

          <m.div variants={staggerItem} className={`${styles.statCard} ${styles.statIndigo}`}>
            <div className={styles.statBlob} />
            <div className={styles.statHeader}>
              <div className={`${styles.statIcon} ${styles.iconIndigo}`}><Layers size={18} /></div>
            </div>
            <div className={`${styles.statValue} ${styles.valueIndigo}`}>{okCount}<span className={styles.statFraction}>/{totalCount}</span></div>
            <span className={styles.statTitle}>{t('dashboard.availableSources')}</span>
          </m.div>
        </div>

        {/* Health ring card */}
        <m.div variants={staggerItem} className={styles.healthCard}>
          <HealthRing pct={healthPct} />
        </m.div>
      </m.div>

      {/* ── Last-updated meta bar ── */}
      <div className={styles.metaBar}>
        <span className={styles.lastUpdated}>
          <span className={styles.lastUpdatedDot} aria-hidden="true" />
          <span className={styles.lastUpdatedLabel}>{t('dashboard.lastUpdated')}</span>
          <span className={styles.lastUpdatedValue}>
            {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}
          </span>
        </span>
        <button
          type="button"
          className={`${styles.refreshBtn} ${loading ? styles.refreshing : ''}`}
          onClick={fetchData}
          disabled={loading}
          aria-label={t('dashboard.refresh')}
        >
          <RefreshCw size={12} />
          {t('dashboard.refresh')}
        </button>
      </div>

      {/* ── Source matrix view ── */}
      <SourceMatrix sources={doctor.sources} />

      {/* ── Source health table ── */}
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>{t('dashboard.sourceHealth')}</h3>
        <p className={styles.sectionDesc}>{t('dashboard.sourceHealthDesc')}</p>
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t('dashboard.status')}</th>
              <th>{t('dashboard.source')}</th>
              <th>{t('dashboard.type')}</th>
              <th>{t('dashboard.tier')}</th>
              <th>{t('dashboard.requiredKey')}</th>
              <th>{t('dashboard.description')}</th>
            </tr>
          </thead>
          <tbody>
            {doctor?.sources.map((src) => (
              <tr key={src.name}>
                <td>
                  <span className={`${styles.dot} ${src.status === 'ok' ? styles.dotOk : styles.dotErr}`} />
                </td>
                <td className={styles.sourceName}>{src.name}</td>
                <td>
                  <Badge color={categoryBadgeColor(src.category)}>
                    {categoryLabel(t, src.category)}
                  </Badge>
                </td>
                <td>
                  <Badge color={integrationBadgeColor(src.integration_type)}>
                    {src.integration_type === 'open_api' ? '公开' : src.integration_type === 'scraper' ? '爬虫' : src.integration_type === 'official_api' ? '授权' : '自建'}
                  </Badge>
                </td>
                <td>
                  <code className={styles.code}>{src.required_key ?? '—'}</code>
                </td>
                <td className={styles.message}>{src.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
