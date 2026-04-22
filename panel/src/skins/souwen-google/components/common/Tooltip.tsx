/**
 * 工具提示组件 - 悬停/焦点显示的信息气泡
 *
 * 文件用途：鼠标悬停或元素获焦时显示的提示气泡，支持四个方向和延时显示
 *
 * 常量：
 *   translateMap - 四个方向的 CSS translate 偏移映射
 *     - top/bottom: x 轴居中，y 轴不变
 *     - left/right: y 轴居中，x 轴不变
 *
 * 函数/类清单：
 *   Tooltip（React.FC<TooltipProps>）
 *     - 功能：包装任意元素以提供悬停提示气泡
 *     - Props:
 *       - content (string): 提示文本内容
 *       - children (ReactNode): 被包装的目标元素
 *       - position (string, 默认 'top'): 气泡位置（'top'|'bottom'|'left'|'right'）
 *       - delay (number, 默认 200): 悬停延迟显示时间（毫秒）
 *     - 交互：mouseEnter/Leave、focus/blur 触发
 *     - 动画：scale up + fade 进入（0.15s），scale down + fade 退出
 */

import { useState, useRef, useCallback, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import styles from './Tooltip.module.scss'

interface TooltipProps {
  content: string
  children: ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

// 四个方向的 CSS translate 偏移配置
const translateMap = {
  top: { x: '-50%', y: 0 },
  bottom: { x: '-50%', y: 0 },
  left: { x: 0, y: '-50%' },
  right: { x: 0, y: '-50%' },
}

export function Tooltip({ content, children, position = 'top', delay = 200 }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(null)

  // 显示提示 - 在指定延迟后显示
  const show = useCallback(() => {
    timer.current = setTimeout(() => setVisible(true), delay)
  }, [delay])

  // 隐藏提示 - 立即隐藏并清理定时器
  const hide = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    setVisible(false)
  }, [])

  const t = translateMap[position]

  return (
    <span className={styles.wrapper} onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children}
      <AnimatePresence>
        {visible && (
          <m.span
            className={`${styles.bubble} ${styles[position]}`}
            role="tooltip"
            style={{ translate: `${t.x} ${t.y}` }}
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.92 }}
            transition={{ duration: 0.15 }}
          >
            {content}
          </m.span>
        )}
      </AnimatePresence>
    </span>
  )
}
