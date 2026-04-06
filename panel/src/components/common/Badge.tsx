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
