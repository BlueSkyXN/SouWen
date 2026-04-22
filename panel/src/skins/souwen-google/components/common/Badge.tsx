/**
 * 徽章组件 - 状态标签显示
 *
 * 文件用途：渲染带有不同颜色的徽章标签，用于展示状态、标签或分类信息
 *
 * 函数/类清单：
 *   Badge（React.FC<BadgeProps>）
 *     - 功能：根据 color 属性应用对应样式并渲染文本内容
 *     - Props:
 *       - color (BadgeColor): 徽章颜色主题（'green'|'blue'|'amber'|'red'|'gray'|'indigo'|'teal'）
 *       - children (ReactNode): 徽章内容文本或节点
 *     - 输出：span 元素，包含颜色类名和内容
 */

import type { ReactNode } from 'react'
import styles from './Badge.module.scss'

type BadgeColor = 'green' | 'blue' | 'amber' | 'red' | 'gray' | 'indigo' | 'teal'

interface BadgeProps {
  color: BadgeColor
  children: ReactNode
}

export function Badge({ color, children }: BadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[color]}`}>
      {children}
    </span>
  )
}
