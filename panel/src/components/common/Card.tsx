import type { ReactNode, CSSProperties } from 'react'

interface CardProps {
  title?: string
  children: ReactNode
  style?: CSSProperties
  className?: string
}

export function Card({ title, children, style, className }: CardProps) {
  return (
    <div
      className={className}
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '20px',
        boxShadow: 'var(--shadow)',
        transition: 'background 0.3s, border-color 0.3s',
        ...style,
      }}
    >
      {title && (
        <div
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--text-secondary)',
            marginBottom: '8px',
            textTransform: 'uppercase',
            letterSpacing: '0.3px',
          }}
        >
          {title}
        </div>
      )}
      {children}
    </div>
  )
}
