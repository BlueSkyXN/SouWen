import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Info, RefreshCw } from 'lucide-react'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { Card } from '../components/common/Card'
import { Spinner } from '../components/common/Spinner'
import { formatError } from '../lib/errors'
import type { ConfigResponse } from '../types'
import styles from './ConfigPage.module.scss'

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

  if (loading) return <Spinner size="lg" label={t('common.loading')} />

  const entries = config ? Object.entries(config) : []

  return (
    <m.div
      className={styles.page}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className={styles.actions}>
        <button
          className="btn btn-primary btn-sm"
          onClick={handleReload}
          disabled={reloading}
        >
          <RefreshCw size={14} />
          {reloading ? t('config.reloading') : t('config.reload')}
        </button>
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div className={styles.infoNote}>
          <Info size={18} />
          <span>{t('config.note')}</span>
        </div>
      </Card>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t('config.key')}</th>
              <th>{t('config.value')}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <td className={styles.configKey}>{key}</td>
                <td className={styles.configValue}>
                  {value === '***' ? (
                    <span className={styles.masked}>{t('config.masked')}</span>
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
    </m.div>
  )
}
