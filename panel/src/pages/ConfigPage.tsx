import { useEffect, useState, useCallback } from 'react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Card } from '../components/common/Card'
import { Spinner } from '../components/common/Spinner'
import type { ConfigResponse } from '../types'
import styles from './ConfigPage.module.scss'

export function ConfigPage() {
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
      addToast('error', `获取配置失败: ${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }, [addToast])

  const handleReload = useCallback(async () => {
    setReloading(true)
    try {
      const res = await api.reloadConfig()
      addToast('success', `配置重载成功${res.password_set ? ' (密码已设置)' : ''}`)
      void fetchConfig()
    } catch (err) {
      addToast('error', `重载失败: ${err instanceof Error ? err.message : '未知错误'}`)
    } finally {
      setReloading(false)
    }
  }, [addToast, fetchConfig])

  useEffect(() => {
    void fetchConfig()
  }, [fetchConfig])

  if (loading) return <Spinner size="lg" label="加载中..." />

  const entries = config ? Object.entries(config) : []

  return (
    <div className={styles.page}>
      {/* Actions */}
      <div className={styles.actions}>
        <button
          className="btn btn-primary btn-sm"
          onClick={handleReload}
          disabled={reloading}
        >
          {reloading ? '重载中...' : '🔄 重载配置'}
        </button>
      </div>

      {/* Info Note */}
      <Card style={{ marginBottom: 24 }}>
        <div className={styles.infoNote}>
          💡 配置项通过服务端的 <code>souwen.yaml</code> 或环境变量进行修改。此处仅供查看，敏感字段已脱敏显示为{' '}
          <code>***</code>。修改配置后可点击「重载配置」使其生效。
        </div>
      </Card>

      {/* Config Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>配置项</th>
              <th>值</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <td className={styles.configKey}>{key}</td>
                <td className={styles.configValue}>
                  {value === '***' ? (
                    <span className={styles.masked}>***</span>
                  ) : value === null || value === undefined ? (
                    <span className={styles.nullVal}>null</span>
                  ) : typeof value === 'object' ? (
                    <code>{JSON.stringify(value)}</code>
                  ) : (
                    <span>{String(value)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
