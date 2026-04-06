import { useEffect, useState, useCallback } from 'react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Badge } from '../components/common/Badge'
import { Spinner } from '../components/common/Spinner'
import type { DoctorResponse, DoctorSource } from '../types'
import styles from './SourcesPage.module.scss'

export function SourcesPage() {
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null)
  const [loading, setLoading] = useState(true)
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

  const okCount = doctor?.ok ?? 0
  const totalCount = doctor?.total ?? 0

  const tiers = [0, 1, 2]
  const sourcesByTier: Record<number, DoctorSource[]> = {}
  for (const tier of tiers) {
    sourcesByTier[tier] = doctor?.sources.filter((s) => s.tier === tier) ?? []
  }

  const tierLabels: Record<number, string> = {
    0: 'Tier 0 — 免费开放',
    1: 'Tier 1 — 需要密钥',
    2: 'Tier 2 — 高级服务',
  }

  const tierColors: Record<number, 'green' | 'blue' | 'amber'> = {
    0: 'green',
    1: 'blue',
    2: 'amber',
  }

  return (
    <div className={styles.page}>
      {/* Summary */}
      <div className={styles.summary}>
        <Badge color={okCount === totalCount ? 'green' : 'amber'}>
          {okCount} / {totalCount} 数据源可用
        </Badge>
        <button className="btn btn-sm btn-outline" onClick={fetchData}>
          🔄 刷新
        </button>
      </div>

      {/* Tier Groups */}
      {tiers.map((tier) => {
        const list = sourcesByTier[tier]
        if (!list || list.length === 0) return null
        return (
          <div key={tier} className={styles.tierGroup}>
            <h3 className={styles.tierTitle}>
              <Badge color={tierColors[tier]}>{tierLabels[tier]}</Badge>
              <span className={styles.tierCount}>({list.length})</span>
            </h3>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>状态</th>
                    <th>名称</th>
                    <th>分类</th>
                    <th>所需配置</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((src) => (
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
      })}
    </div>
  )
}
