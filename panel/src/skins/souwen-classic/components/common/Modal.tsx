/**
 * 模态对话框组件 - 中心弹窗/对话框
 *
 * 文件用途：提供带动画的模态对话框组件，支持标题、内容、操作按钮和键盘/点击外部关闭
 *
 * 函数/类清单：
 *   Modal（React.FC<ModalProps>）
 *     - 功能：渲染层级浮窗模态框，支持动画进出和键盘/外部点击关闭
 *     - Props:
 *       - open (boolean): 模态框显示状态
 *       - onClose (() => void): 关闭回调（当用户按 ESC、点击外部或关闭按钮）
 *       - title (string): 对话框标题
 *       - children (ReactNode): 对话框体内容
 *       - actions (ReactNode, 可选): 底部操作按钮区域
 *     - 交互：
 *       - ESC 键关闭
 *       - 点击外部背景关闭
 *       - 点击卡片不触发关闭
 *     - 动画：背景 fade（0.18s）+ 卡片 spring scale（400/28 刚度/阻尼）
 */

import { useEffect, useCallback, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { X } from 'lucide-react'
import styles from './Modal.module.scss'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  actions?: ReactNode
}

export function Modal({ open, onClose, title, children, actions }: ModalProps) {
  // ESC 键处理
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose],
  )

  useEffect(() => {
    if (!open) return
    // 模态框打开时注册 ESC 键监听
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  return (
    <AnimatePresence>
      {open && (
        // 背景遮罩层 - 点击关闭对话框
        <m.div
          className={styles.overlay}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
        >
          {/* 对话框卡片 - 点击时阻止事件冒泡，不触发关闭 */}
          <m.div
            className={styles.card}
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.92 }}
            transition={{ type: 'spring', stiffness: 400, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.header}>
              <h2 className={styles.title}>{title}</h2>
              {/* 关闭按钮 */}
              <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className={styles.body}>{children}</div>
            {/* 操作按钮区域（可选） */}
            {actions && <div className={styles.actions}>{actions}</div>}
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
