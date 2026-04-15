import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react'
import styles from './Input.module.scss'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  description?: string
  error?: string
  icon?: ReactNode
  suffix?: ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, description, error, icon, suffix, className, id, ...rest }, ref) => {
    const inputId = id ?? (label ? `input-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined)

    const inputCls = [
      styles.input,
      icon ? styles.hasIcon : '',
      suffix ? styles.hasSuffix : '',
      error ? styles.error : '',
      className ?? '',
    ]
      .filter(Boolean)
      .join(' ')

    return (
      <div className={styles.wrapper}>
        {label && (
          <label htmlFor={inputId} className={styles.label}>
            {label}
          </label>
        )}
        {description && <span className={styles.description}>{description}</span>}
        <div className={styles.inputWrap}>
          {icon && <span className={styles.icon}>{icon}</span>}
          <input ref={ref} id={inputId} className={inputCls} {...rest} />
          {suffix && <span className={styles.suffix}>{suffix}</span>}
        </div>
        {error && <span className={styles.errorMsg}>{error}</span>}
      </div>
    )
  },
)

Input.displayName = 'Input'
