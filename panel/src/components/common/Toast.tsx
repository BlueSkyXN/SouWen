import { AnimatePresence, m } from 'framer-motion'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { useNotificationStore } from '../../stores/notificationStore'
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
              initial={{ opacity: 0, y: -12, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              onClick={() => removeToast(toast.id)}
            >
              <span className={styles.icon}>
                <Icon size={18} />
              </span>
              <span style={{ flex: 1 }}>{toast.message}</span>
              <X size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
            </m.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
