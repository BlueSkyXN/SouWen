/**
 * 文件用途：Apple 皮肤的消息提示组件，展示系统或操作反馈消息
 *
 * 组件/函数清单：
 *   ToastContainer（函数组件）
 *     - 功能：管理并渲染多个 Toast 消息，支持自动淡出或点击关闭，支持 success/error/info 三种类型
 *     - 依赖：从 notificationStore 读取 toasts 列表和 removeToast 移除函数
 *     - 输出：展示 Toast 列表的 React 元素，使用 framer-motion 实现进出动画
 *     - 关键常量：ICONS 类型对应的图标映射（success→CheckCircle2, error→XCircle, info→Info）
 *
 * 模块依赖：
 *   - framer-motion: 动画库，用于 Toast 进出动画
 *   - lucide-react: 图标库，提供 CheckCircle2、XCircle、Info、X 等图标
 *   - @core/stores/notificationStore: Zustand store 管理消息队列
 *   - ./Toast.module.scss: Toast 容器和单个 Toast 项的样式
 */

import { AnimatePresence, m } from 'framer-motion'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { useNotificationStore } from '@core/stores/notificationStore'
import styles from './Toast.module.scss'

/**
 * Toast 类型与对应图标的映射
 * 'as const' 确保类型推导为精确的字符串字面量类型
 */
const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
} as const

/**
 * ToastContainer 组件 - 消息提示容器
 * 从全局 notification store 读取 toasts 列表，动画展示并支持点击关闭
 * 使用 AnimatePresence 在列表变化时平滑进出动画
 * @returns {JSX.Element} Toast 消息列表容器
 */
export function ToastContainer() {
  // 从 zustand store 获取 toasts 列表和移除函数
  const toasts = useNotificationStore((s) => s.toasts)
  const removeToast = useNotificationStore((s) => s.removeToast)

  return (
    <div className={styles.container}>
      <AnimatePresence>
        {toasts.map((toast) => {
          // 根据 toast.type 查找对应的图标组件
          const Icon = ICONS[toast.type]
          return (
            // framer-motion 包裹的动画 div，点击时移除该 toast
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
