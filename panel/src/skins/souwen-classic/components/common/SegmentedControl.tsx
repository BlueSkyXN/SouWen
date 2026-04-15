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
  const [indicator, setIndicator] = useState({ left: 0, width: 0, height: 0 })

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
    // Re-measure on resize
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure])

  return (
    <div className={styles.container} ref={containerRef} role="tablist">
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
          {opt.icon && <span className={styles.iconSlot}>{opt.icon}</span>}
          {opt.label}
        </button>
      ))}
    </div>
  )
}
