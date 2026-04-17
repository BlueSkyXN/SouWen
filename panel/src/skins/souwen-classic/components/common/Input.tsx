/**
 * 输入框组件 - 带标签/描述/错误提示的表单输入
 *
 * 文件用途：提供可复用的输入框组件，支持标签、描述文本、前置/后置图标、错误提示
 *
 * 函数/类清单：
 *   Input（forwardRef<HTMLInputElement, InputProps>）
 *     - 功能：渲染完整的输入框 UI，包括标签、描述、错误提示及图标槽
 *     - Props:
 *       - label (string, 可选): 输入框标签
 *       - description (string, 可选): 辅助说明文本
 *       - error (string, 可选): 错误信息，显示时输入框边框变红
 *       - icon (ReactNode, 可选): 前置图标
 *       - suffix (ReactNode, 可选): 后置元素（如单位、按钮）
 *       - ...rest: 标准 input HTML 属性
 *     - 输出：div 包装的完整表单控件
 *     - 自动生成 ID：若未提供 id 但提供 label，自动生成 input-{label}
 */

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
    // 自动生成输入框 ID（基于标签文本）
    const inputId = id ?? (label ? `input-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined)

    // 构建输入框类名：基础 + 图标状态 + 后缀状态 + 错误状态 + 自定义
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
        {/* 标签和辅助说明 */}
        {label && (
          <label htmlFor={inputId} className={styles.label}>
            {label}
          </label>
        )}
        {description && <span className={styles.description}>{description}</span>}
        <div className={styles.inputWrap}>
          {/* 前置图标 */}
          {icon && <span className={styles.icon}>{icon}</span>}
          <input ref={ref} id={inputId} className={inputCls} {...rest} />
          {/* 后置元素（如单位、按钮） */}
          {suffix && <span className={styles.suffix}>{suffix}</span>}
        </div>
        {/* 错误提示信息 */}
        {error && <span className={styles.errorMsg}>{error}</span>}
      </div>
    )
  },
)

Input.displayName = 'Input'
