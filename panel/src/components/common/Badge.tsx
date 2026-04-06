import type { ReactNode } from 'react'

type BadgeColor = 'green' | 'blue' | 'amber' | 'red' | 'gray'

interface BadgeProps {
  color: BadgeColor
  children: ReactNode
}

const colorMap: Record<BadgeColor, { bg: string; text: string }> = {
  green: { bg: 'var(--success-light)', text: 'var(--success)' },
  blue: { bg: 'var(--primary-light)', text: 'var(--primary)' },
  amber: { bg: 'var(--warning-light)', text: 'var(--warning)' },
  red: { bg: 'var(--error-light)', text: 'var(--error)' },
  gray: { bg: 'var(--border)', text: 'var(--text-secondary)' },
}

export function Badge({ color, children }: BadgeProps) {
  const c = colorMap[color]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 10px',
        borderRadius: '99px',
        fontSize: '12px',
        fontWeight: 500,
        lineHeight: 1.6,
        background: c.bg,
        color: c.text,
      }}
    >
      {children}
    </span>
  )
}
