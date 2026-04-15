import { useState, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import styles from './Accordion.module.scss'

interface AccordionProps {
  title: string
  description?: string
  defaultOpen?: boolean
  children: ReactNode
  icon?: ReactNode
}

export function Accordion({ title, description, defaultOpen = false, children, icon }: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`${styles.accordion} ${open ? styles.open : ''}`}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {icon && <span className={styles.iconSlot}>{icon}</span>}
        <div className={styles.titleGroup}>
          <div className={styles.title}>{title}</div>
          {description && <div className={styles.description}>{description}</div>}
        </div>
        <ChevronDown
          size={16}
          className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <m.div
            className={styles.content}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
          >
            <div className={styles.inner}>{children}</div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
