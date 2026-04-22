/**
 * 加载微调器组件 - 旋转加载指示器
 *
 * 文件用途：显示数据加载状态的旋转加载图标，支持多种尺寸和可选标签
 *
 * 函数/类清单：
 *   Spinner（React.FC<SpinnerProps>）
 *     - 功能：渲染带旋转动画的加载器，可选显示标签文本
 *     - Props:
 *       - size (string, 默认 'md'): 加载器尺寸（'sm'|'md'|'lg'）
 *       - label (string, 可选): 加载标签文本，显示在图标下方
 *     - 样式：使用 CSS 变量 --primary 和 --text-secondary 的颜色
 *     - 动画：连续旋转（0.6s/周期）
 */

import { Loader2 } from 'lucide-react'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export function Spinner({ size = 'md', label }: SpinnerProps) {
  // 根据 size 确定图标尺寸
  const dim = size === 'sm' ? 20 : size === 'lg' ? 36 : 24
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px',
        gap: '12px',
        color: 'var(--text-secondary)',
        fontSize: '13px',
      }}
    >
      {/* 旋转加载图标 */}
      <Loader2
        size={dim}
        style={{ animation: 'spin 0.6s linear infinite' }}
        color="var(--primary)"
      />
      {/* 可选的加载标签 */}
      {label && <span>{label}</span>}
    </div>
  )
}
