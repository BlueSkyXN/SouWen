import { AnimatePresence, m } from 'framer-motion'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { useNotificationStore } from '@core/stores/notificationStore'
import styles from './Toast.module.scss'

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
} as const

export function ToastContainer() {
  const toasts = useNotificationStore((s) => s.toasts)
  const removeToast = useNotificationStore((s) => s.removeToast)

  return (
    <div className={styles.container}>
      <AnimatePresence>
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type]
          return (
            <m.div
              key={toast.id}
              className={`${styles.toast} ${styles[toast.type]}`}
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 40 }}
              transition={{ duration: 0.2 }}
              onClick={() => removeToast(toast.id)}
            >
              <span className={styles.icon}>
                <Icon size={16} />
              </span>
              <span style={{ flex: 1 }}>{toast.message}</span>
              <X size={12} className={styles.closeIcon} />
            </m.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
