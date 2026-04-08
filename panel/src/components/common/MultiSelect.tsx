import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
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
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const filterRef = useRef<HTMLInputElement>(null)

  // Close on outside click
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

  // Focus filter when opened
  useEffect(() => {
    if (open) filterRef.current?.focus()
  }, [open])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setFilter('')
      }
    },
    [],
  )

  const toggle = useCallback(
    (value: string) => {
      const next = selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value]
      onChange(next)
    },
    [selected, onChange],
  )

  const remove = useCallback(
    (value: string) => {
      onChange(selected.filter((v) => v !== value))
    },
    [selected, onChange],
  )

  const selectAll = useCallback(() => {
    onChange(options.map((o) => o.value))
    setFilter('')
  }, [options, onChange])

  const clearAll = useCallback(() => {
    onChange([])
  }, [onChange])

  const filtered = filter
    ? options.filter(
        (o) =>
          o.value.toLowerCase().includes(filter.toLowerCase()) ||
          o.label.toLowerCase().includes(filter.toLowerCase()),
      )
    : options

  const selectedLabels = new Map(options.map((o) => [o.value, o.label]))

  return (
    <div className={styles.container} ref={containerRef} onKeyDown={handleKeyDown}>
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
          {selected.length === 0 && (
            <span className={styles.placeholder}>{placeholder}</span>
          )}
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
                aria-label={`Remove ${val}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
        <ChevronDown size={16} className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`} />
      </div>

      {open && (
        <div className={styles.dropdown} role="listbox">
          <div className={styles.dropdownHeader}>
            <input
              ref={filterRef}
              type="text"
              className={styles.filterInput}
              placeholder="Filter..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div className={styles.actions}>
              <button type="button" className={styles.actionBtn} onClick={selectAll}>
                All
              </button>
              <button type="button" className={styles.actionBtn} onClick={clearAll}>
                Clear
              </button>
            </div>
          </div>
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
                    {opt.needsKey && (
                      <span className={styles.keyBadge} title="Requires API key">
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
            {filtered.length === 0 && (
              <div className={styles.noResults}>No matching sources</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
