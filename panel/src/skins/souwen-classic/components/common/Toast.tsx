/**
 * 消息提示容器组件 - 全局 toast 消息队列
 *
 * 文件用途：连接到通知 store，渲染堆叠式 toast 消息，支持成功/错误/信息三种类型
 *
 * 常量/类型：
 *   ICONS - 消息类型到图标组件的映射
 *     - success: CheckCircle2（绿色勾选）
 *     - error: XCircle（红色叉号）
 *     - info: Info（蓝色信息）
 *
 * 函数/类清单：
 *   ToastContainer（React.FC）
 *     - 功能：从 store 获取 toast 列表并渲染消息队列，支持点击关闭
 *     - 依赖：useNotificationStore
 *     - 交互：点击 toast 立即移除，支持 AnimatePresence 动画
 *     - 动画：进入 scale up + fade（0.2s），退出 scale down + fade
 */

import { AnimatePresence, m } from 'framer-motion'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { useNotificationStore } from '@core/stores/notificationStore'
import styles from './Toast.module.scss'

// 消息类型到图标的映射
const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
} as const

export function ToastContainer() {
  // 获取 toast 列表和移除函数
  const toasts = useNotificationStore((s) => s.toasts)
  const removeToast = useNotificationStore((s) => s.removeToast)

  return (
    <div className={styles.container}>
      <AnimatePresence>
        {toasts.map((toast) => {
          // 根据 toast 类型选择图标
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
              {/* 消息类型图标 */}
              <span className={styles.icon}>
                <Icon size={18} />
              </span>
              {/* 消息内容 */}
              <span style={{ flex: 1 }}>{toast.message}</span>
              {/* 关闭图标提示 */}
              <X size={14} style={{ flexShrink: 0, opacity: 0.7 }} />
            </m.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
