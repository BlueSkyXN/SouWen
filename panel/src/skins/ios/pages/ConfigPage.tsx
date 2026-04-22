/**
 * 文件用途：iOS 皮肤的配置页面
 *
 * 提供两种编辑模式：
 *   1. 源文件编辑 — CodeMirror YAML 编辑器
 *   2. 可视化编辑 — 分节表单编辑器
 */

import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Settings, RefreshCw } from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { ConfigEditorPanel } from '@core/components/ConfigEditor'
import styles from './ConfigPage.module.scss'

export function ConfigPage() {
  const { t } = useTranslation()
  const [reloading, setReloading] = useState(false)
  const addToast = useNotificationStore((s) => s.addToast)

  const handleReload = useCallback(async () => {
    setReloading(true)
    try {
      const res = await api.reloadConfig()
      let msg = t('config.reloadSuccess')
      if (res.password_set) msg += ` ${t('config.passwordSet')}`
      addToast('success', msg)
    } catch (err) {
      addToast('error', t('config.reloadFailed', { message: formatError(err) }))
    } finally {
      setReloading(false)
    }
  }, [addToast, t])

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>
            <Settings size={20} />
            {t('config.title', 'Configuration')}
          </h1>
          <p className={styles.pageDesc}>{t('config.note')}</p>
        </div>
        <button className={styles.commitBtn} onClick={() => void handleReload()} disabled={reloading}>
          <RefreshCw size={14} />
          {reloading ? t('config.reloading') : t('config.reload', 'Reload Configuration')}
        </button>
      </m.div>

      <m.div variants={staggerItem}>
        <ConfigEditorPanel />
      </m.div>
    </m.div>
  )
}
