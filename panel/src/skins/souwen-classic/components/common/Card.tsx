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
      {title && <div className={styles.title}>{title}</div>}
      {children}
    </div>
  )
}
