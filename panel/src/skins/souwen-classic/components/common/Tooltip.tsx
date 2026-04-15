import { useState, useRef, useCallback, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import styles from './Tooltip.module.scss'

interface TooltipProps {
  content: string
  children: ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

const translateMap = {
  top: { x: '-50%', y: 0 },
  bottom: { x: '-50%', y: 0 },
  left: { x: 0, y: '-50%' },
  right: { x: 0, y: '-50%' },
}

export function Tooltip({ content, children, position = 'top', delay = 200 }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(null)

  const show = useCallback(() => {
    timer.current = setTimeout(() => setVisible(true), delay)
  }, [delay])

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
