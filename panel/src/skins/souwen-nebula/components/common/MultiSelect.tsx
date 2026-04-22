/**
 * 多选下拉列表组件 - 支持搜索、全选/清空的多选器
 *
 * 文件用途：提供带过滤、全选/清空功能的多选下拉列表，支持键盘导航和 ARIA 无障碍
 *
 * 类型定义：
 *   SelectOption - 选项数据结构
 *     - value (string): 选项值
 *     - label (string): 显示标签
 *     - description (string, 可选): 选项说明
 *     - needsKey (boolean, 可选): 是否需要 API 密钥（显示 Key 徽章）
 *
 * 函数/类清单：
 *   MultiSelect（React.FC<MultiSelectProps>）
 *     - 功能：渲染多选下拉列表，支持搜索、全选、清空、单项切换
 *     - Props:
 *       - options (SelectOption[]): 完整选项列表
 *       - selected (string[]): 已选项值数组
 *       - onChange ((selected: string[]) => void): 选项变更回调
 *       - placeholder (string, 可选): 未选时提示文本
 *     - 交互特性：
 *       - 点击触发器展开/收缩
 *       - 支持 Enter/Space 键打开
 *       - ESC 关闭并清空搜索
 *       - 外部点击自动关闭
 *       - 搜索过滤列表
 *       - 每项可独立切换、通过芯片快速移除
 *     - 无障碍：combobox + listbox role、aria-expanded、aria-selected
 */

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, X, KeyRound } from 'lucide-react'
import styles from './MultiSelect.module.scss'

export interface SelectOption {
  value: string
  label: string
  description?: string
  needsKey?: boolean
}

interface MultiSelectProps {
  options: SelectOption[]
  selected: string[]
  onChange: (selected: string[]) => void
  placeholder?: string
}

export function MultiSelect({ options, selected, onChange, placeholder }: MultiSelectProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const filterRef = useRef<HTMLInputElement>(null)

  // 外部点击关闭下拉列表
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setFilter('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // 打开时自动聚焦搜索框
  useEffect(() => {
    if (open) filterRef.current?.focus()
  }, [open])

  // ESC 键关闭并清空搜索
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setFilter('')
      }
    },
    [],
  )

  // 单个选项切换（添加或移除）
  const toggle = useCallback(
    (value: string) => {
      const next = selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value]
      onChange(next)
    },
    [selected, onChange],
  )

  // 移除指定选项
  const remove = useCallback(
    (value: string) => {
      onChange(selected.filter((v) => v !== value))
    },
    [selected, onChange],
  )

  // 全选所有选项
  const selectAll = useCallback(() => {
    onChange(options.map((o) => o.value))
    setFilter('')
  }, [options, onChange])

  // 清空所有选项
  const clearAll = useCallback(() => {
    onChange([])
  }, [onChange])

  // 根据搜索词过滤选项
  const filtered = filter
    ? options.filter(
        (o) =>
          o.value.toLowerCase().includes(filter.toLowerCase()) ||
          o.label.toLowerCase().includes(filter.toLowerCase()),
      )
    : options

  // 构建 value -> label 映射，用于显示已选项标签
  const selectedLabels = new Map(options.map((o) => [o.value, o.label]))

  return (
    <div className={styles.container} ref={containerRef} onKeyDown={handleKeyDown}>
      {/* 触发器区域 - 显示已选项的芯片和下拉箭头 */}
      <div
        className={`${styles.trigger} ${open ? styles.triggerOpen : ''}`}
        onClick={() => setOpen(!open)}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen(!open)
          }
        }}
      >
        <div className={styles.chips}>
          {/* 未选时显示占位符 */}
          {selected.length === 0 && (
            <span className={styles.placeholder}>{placeholder}</span>
          )}
          {/* 已选项芯片 - 带快速移除按钮 */}
          {selected.map((val) => (
            <span key={val} className={styles.chip}>
              {selectedLabels.get(val) ?? val}
              <button
                type="button"
                className={styles.chipRemove}
                onClick={(e) => {
                  e.stopPropagation()
                  remove(val)
                }}
                aria-label={`${t('common.cancel')} ${val}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
        {/* 下拉指示器箭头 */}
        <ChevronDown size={16} className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`} />
      </div>

      {/* 下拉菜单 */}
      {open && (
        <div className={styles.dropdown} role="listbox">
          {/* 头部：搜索框 + 全选/清空按钮 */}
          <div className={styles.dropdownHeader}>
            <input
              ref={filterRef}
              type="text"
              className={styles.filterInput}
              placeholder={t('multiselect.filter')}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div className={styles.actions}>
              <button type="button" className={styles.actionBtn} onClick={selectAll} aria-label={t('multiselect.selectAll')}>
                {t('multiselect.selectAll')}
              </button>
              <button type="button" className={styles.actionBtn} onClick={clearAll} aria-label={t('multiselect.clearAll')}>
                {t('multiselect.clearAll')}
              </button>
            </div>
          </div>
          {/* 选项列表 */}
          <div className={styles.optionsList}>
            {filtered.map((opt) => {
              const isSelected = selected.includes(opt.value)
              return (
                <label
                  key={opt.value}
                  className={`${styles.option} ${isSelected ? styles.optionSelected : ''}`}
                  role="option"
                  aria-selected={isSelected}
                >
                  <input
                    type="checkbox"
                    className={styles.checkbox}
                    checked={isSelected}
                    onChange={() => toggle(opt.value)}
                  />
                  <div className={styles.optionContent}>
                    <span className={styles.optionLabel}>{opt.label}</span>
                    {/* 需要 API 密钥时显示 Key 徽章 */}
                    {opt.needsKey && (
                      <span className={styles.keyBadge} title={t('multiselect.needsKey')}>
                        <KeyRound size={10} />
                        Key
                      </span>
                    )}
                  </div>
                  {opt.description && (
                    <span className={styles.optionDesc}>{opt.description}</span>
                  )}
                </label>
              )
            })}
            {/* 无搜索结果提示 */}
            {filtered.length === 0 && (
              <div className={styles.noResults}>{t('multiselect.noResults')}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
