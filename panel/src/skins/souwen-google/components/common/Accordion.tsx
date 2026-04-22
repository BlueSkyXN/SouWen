/**
 * 手风琴组件 - 可展开/收缩的内容容器
 *
 * 文件用途：提供带动画的手风琴交互组件，支持标题、描述、自定义图标及内容展开/收缩
 *
 * 函数/类清单：
 *   Accordion（React.FC<AccordionProps>）
 *     - 功能：渲染可控制展开/收缩状态的手风琴组件
 *     - Props:
 *       - title (string): 手风琴标题
 *       - description (string, 可选): 副标题描述文本
 *       - defaultOpen (boolean, 默认 false): 初始是否展开
 *       - children (ReactNode): 手风琴体内容
 *       - icon (ReactNode, 可选): 标题左侧图标
 *     - 交互：点击触发器区域切换展开/收缩，支持 aria-expanded 无障碍属性
 *     - 动画：使用 framer-motion 实现 height 和 opacity 过渡（0.22s）
 */

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
  // 控制手风琴展开/收缩状态
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`${styles.accordion} ${open ? styles.open : ''}`}>
      {/* 触发器按钮 - 点击切换展开状态 */}
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
      {/* 内容区域 - 通过 AnimatePresence 控制挂载/卸载，framer-motion 提供动画 */}
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
