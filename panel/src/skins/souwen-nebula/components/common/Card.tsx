/**
 * 卡片组件 - 内容容器
 *
 * 文件用途：提供带可选标题的卡片样式容器，用于分组和展示内容
 *
 * 函数/类清单：
 *   Card（React.FC<CardProps>）
 *     - 功能：渲染卡片容器，可选择在顶部显示标题
 *     - Props:
 *       - title (string, 可选): 卡片标题
 *       - children (ReactNode): 卡片内容
 *       - style (CSSProperties, 可选): 内联样式对象
 *       - className (string, 可选): 额外的 CSS 类名
 *     - 输出：div 元素，包含标题（可选）和内容
 */

import type { ReactNode, CSSProperties } from 'react'
import styles from './Card.module.scss'

interface CardProps {
  title?: string
  children: ReactNode
  style?: CSSProperties
  className?: string
}

export function Card({ title, children, style, className }: CardProps) {
  return (
    <div className={`${styles.card} ${className ?? ''}`} style={style}>
      {/* 条件渲染标题区域 */}
      {title && <div className={styles.title}>{title}</div>}
      {children}
    </div>
  )
}
