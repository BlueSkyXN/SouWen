/**
 * 按钮组件 - 通用交互按钮
 *
 * 文件用途：提供多种样式变体（primary/secondary/ghost/danger/success/outline）和尺寸（sm/md/lg）的可复用按钮组件
 *
 * 函数/类清单：
 *   Button（React.FC<ButtonProps>）
 *     - 功能：渲染样式化的 HTML button 元素，支持加载状态、图标、禁用态
 *     - Props:
 *       - variant (string, 默认 'primary'): 按钮视觉样式主题
 *       - size (string, 默认 'md'): 按钮尺寸（影响内外边距、字体大小）
 *       - loading (boolean, 默认 false): 是否显示加载状态（旋转加载图标）
 *       - icon (ReactNode, 可选): 按钮前的图标
 *       - block (boolean, 默认 false): 是否以块级元素全宽显示
 *       - disabled (boolean, 可选): 禁用状态
 *       - ...rest: 标准 button HTML 属性
 *     - 交互：loading 时自动禁用，点击可触发 onClick 处理
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import styles from './Button.module.scss'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
  block?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  block = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  // 动态构建类名：基础样式 + 变体 + 尺寸 + block 模式 + 自定义类
  const cls = [
    styles.button,
    styles[variant],
    styles[size],
    block ? styles.block : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={cls} disabled={disabled || loading} {...rest}>
      {/* loading 时显示旋转加载图标；否则显示自定义图标（如果提供）或无图标 */}
      {loading ? (
        <Loader2 size={size === 'sm' ? 14 : 16} className={styles.spinner} />
      ) : icon ? (
        <span className={styles.iconSlot}>{icon}</span>
      ) : null}
      {children}
    </button>
  )
}
