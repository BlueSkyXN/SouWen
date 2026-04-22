/**
 * 分段控制组件 - 标签切换器，带动画指示条
 *
 * 文件用途：提供按钮组切换器，支持泛型值、动画指示条和响应式 resize 处理
 *
 * 类型定义：
 *   SegmentOption<T> - 单个选项配置
 *     - value (T): 选项值
 *     - label (string): 显示标签
 *     - icon (ReactNode, 可选): 选项图标
 *
 * 函数/类清单：
 *   SegmentedControl<T>（React.FC<SegmentedControlProps<T>>）
 *     - 功能：渲染多个按钮选项，当前选项下方有动画指示条
 *     - Props:
 *       - options (SegmentOption<T>[]): 选项列表
 *       - value (T): 当前选中值
 *       - onChange ((value: T) => void): 选项变更回调
 *     - 交互：点击任意按钮切换选项，指示条通过 spring 动画平滑移动
 *     - 响应式：窗口 resize 时重新测量指示条位置
 */

import { useRef, useState, useEffect, useCallback, type ReactNode } from 'react'
import { m, AnimatePresence } from 'framer-motion'
import styles from './SegmentedControl.module.scss'

interface SegmentOption<T extends string> {
  value: T
  label: string
  icon?: ReactNode
}

interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null)
  // 指示条位置和尺寸：{ left, width, height }
  const [indicator, setIndicator] = useState({ left: 0, width: 0, height: 0 })

  // 测量当前选中按钮的位置和大小，更新指示条
  const measure = useCallback(() => {
    if (!containerRef.current) return
    const active = containerRef.current.querySelector(`[data-value="${value}"]`) as HTMLElement | null
    if (!active) return
    setIndicator({
      left: active.offsetLeft,
      width: active.offsetWidth,
      height: active.offsetHeight,
    })
  }, [value])

  useEffect(() => {
    measure()
    // 窗口 resize 时重新测量
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure])

  return (
    <div className={styles.container} ref={containerRef} role="tablist">
      {/* 动画指示条背景 */}
      <AnimatePresence initial={false}>
        <m.div
          className={styles.indicator}
          layout
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          style={{
            position: 'absolute',
            top: 3,
            left: indicator.left,
            width: indicator.width,
            height: indicator.height,
          }}
        />
      </AnimatePresence>
      {/* 选项按钮组 */}
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={opt.value === value}
          data-value={opt.value}
          className={`${styles.option} ${opt.value === value ? styles.active : ''}`}
          onClick={() => onChange(opt.value)}
        >
          {/* 可选的选项图标 */}
          {opt.icon && <span className={styles.iconSlot}>{opt.icon}</span>}
          {opt.label}
        </button>
      ))}
    </div>
  )
}
