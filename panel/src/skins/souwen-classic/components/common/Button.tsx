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
      {loading ? (
        <Loader2 size={size === 'sm' ? 14 : 16} className={styles.spinner} />
      ) : icon ? (
        <span className={styles.iconSlot}>{icon}</span>
      ) : null}
      {children}
    </button>
  )
}
