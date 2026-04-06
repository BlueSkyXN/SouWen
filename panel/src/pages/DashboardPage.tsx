import { useEffect, useState, useCallback } from 'react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { useAuthStore } from '../stores/authStore'
import { Card } from '../components/common/Card'
import { Badge } from '../components/common/Badge'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse } from '../types'
import styles from './DashboardPage.module.scss'

export function DashboardPage() {
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const version = useAuthStore((s) => s.version)
  const addToast = useNotificationStore((s) => s.addToast)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.getDoctor()
      setDoctor(d)
    } catch (err) {
      addToast('error', `获取数据失败: ${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  if (loading) return <Spinner size="lg" label="加载中..." />

  const paperCount = doctor?.sources.filter((s) => s.category === 'paper').length ?? 0
  const patentCount = doctor?.sources.filter((s) => s.category === 'patent').length ?? 0
  const webCount = doctor?.sources.filter((s) => s.category === 'web').length ?? 0
  const okCount = doctor?.ok ?? 0
  const totalCount = doctor?.total ?? 0
  const healthPct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0

  return (
    <div className={styles.page}>
      {/* Server Info */}
      <Card style={{ marginBottom: 24 }}>
        <div className={styles.serverInfo}>
          <div>
            <span className={styles.serverLabel}>服务状态</span>
            <Badge color="green">运行中</Badge>
          </div>
          <div>
            <span className={styles.serverLabel}>版本</span>
            <span className={styles.serverValue}>{version || '未知'}</span>
          </div>
          <div>
            <span className={styles.serverLabel}>可用数据源</span>
            <span className={styles.serverValue}>
              {okCount} / {totalCount}
            </span>
          </div>
        </div>
      </Card>

      {/* Stats Grid */}
      <div className={styles.statsGrid}>
        <Card title="论文数据源">
          <div className={styles.cardValue}>{paperCount}</div>
        </Card>
        <Card title="专利数据源">
          <div className={styles.cardValue}>{patentCount}</div>
        </Card>
        <Card title="网页搜索引擎">
          <div className={styles.cardValue}>{webCount}</div>
        </Card>
        <Card title="可用数据源">
          <div className={styles.cardValue}>
            {okCount} / {totalCount}
          </div>
        </Card>
        <Card title="健康度">
          <div
            className={styles.cardValue}
            style={{ color: healthPct >= 80 ? 'var(--success)' : healthPct >= 50 ? 'var(--warning)' : 'var(--error)' }}
          >
            {healthPct}%
          </div>
        </Card>
      </div>

      {/* Doctor Table */}
      <h3 className={styles.sectionTitle}>数据源健康检查</h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>状态</th>
              <th>数据源</th>
              <th>分类</th>
              <th>层级</th>
              <th>所需配置</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {doctor?.sources.map((src) => (
              <tr key={src.name}>
                <td>{src.status === 'ok' ? '✅' : '⬜'}</td>
                <td className={styles.sourceName}>{src.name}</td>
                <td>
                  <Badge
                    color={
                      src.category === 'paper'
                        ? 'blue'
                        : src.category === 'patent'
                          ? 'amber'
                          : 'green'
                    }
                  >
                    {src.category === 'paper'
                      ? '论文'
                      : src.category === 'patent'
                        ? '专利'
                        : '网页'}
                  </Badge>
                </td>
                <td>
                  <Badge
                    color={
                      src.tier === 0
                        ? 'green'
                        : src.tier === 1
                          ? 'blue'
                          : 'amber'
                    }
                  >
                    Tier {src.tier}
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
