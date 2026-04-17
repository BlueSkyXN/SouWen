/**
 * 文件用途：动画预设库，提供符合 Apple 设计风格的 Spring-based 动画配置集
 *
 * 导出项清单：
 *     staggerContainer（对象）
 *         - 功能：容器动画预设，为子元素应用错位延迟效果
 *         - 配置：staggerChildren 0.04s，delayChildren 0.02s
 *         - 用途：列表、栅格等多元素组合进入动画
 *
 *     staggerContainerFast（对象）
 *         - 功能：快速错位动画，适合高密度元素列表
 *         - 配置：staggerChildren 0.025s
 *
 *     staggerItem（对象）
 *         - 功能：单个列表项动画预设，配合 staggerContainer 使用
 *         - 初始状态：opacity 0, 向下偏移 12px（y: 12）
 *         - 动画状态：opacity 1, y 0，使用 spring 动画（stiffness 400, damping 28）
 *
 *     staggerItemSmall（对象）
 *         - 功能：微量偏移的列表项动画，适合紧凑布局
 *         - 初始状态：opacity 0, y 6
 *         - 动画状态：opacity 1, y 0，spring 参数（stiffness 500, damping 30）
 *
 *     fadeInUp（对象）
 *         - 功能：通用淡入上升动画，用于单个元素出现
 *         - 初始状态：opacity 0, y 10
 *         - 动画状态：opacity 1, y 0，spring（stiffness 380, damping 26）
 *
 *     fadeIn（对象）
 *         - 功能：纯淡入动画，透明度变化无位移
 *         - 初始状态：opacity 0
 *         - 动画状态：opacity 1，duration 0.25s（线性）
 *
 *     scaleIn（对象）
 *         - 功能：缩放进入动画，从 95% 缩放到 100%
 *         - 初始状态：opacity 0, scale 0.95
 *         - 动画状态：opacity 1, scale 1，spring（stiffness 400, damping 25）
 *
 *     slideInRight（对象）
 *         - 功能：从右侧滑入动画，用于侧栏、抽屉等
 *         - 初始状态：opacity 0，从右侧 16px 外进入（x: 16）
 *         - 动画状态：opacity 1, x 0，spring（stiffness 400, damping 28）
 *
 * 设计哲学：
 *     所有 spring 动画参数经调优，以达到 Apple 风格的流畅、自然、不过度弹性的效果
 *     stiffness（刚度）控制动画快速性，damping（阻尼）控制摆荡减弱速度
 */

// Spring-based animation presets for natural, Apple-like motion

/**
 * 容器错位动画预设
 * 为多个子元素提供级联进入效果，每个子元素间隔 0.04s 错开
 */
export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
} as const

/**
 * 快速容器错位动画预设
 * 子元素间隔缩短到 0.025s，适合高密度列表
 */
export const staggerContainerFast = {
  animate: { transition: { staggerChildren: 0.025 } },
} as const

/**
 * 列表项动画预设
 * 单个元素从透明 + 向下偏移 12px，使用弹簧效果平滑进入
 */
export const staggerItem = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 400, damping: 28 } },
}

/**
 * 小型列表项动画预设
 * 偏移量减少到 6px，动画参数更敏捷（stiffness 提升到 500）
 */
export const staggerItemSmall = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 500, damping: 30 } },
}

/**
 * 通用淡入上升动画
 * 单个元素从透明 + 下移 10px 进入，适合对话框、通知等独立元素
 */
export const fadeInUp = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { type: 'spring' as const, stiffness: 380, damping: 26 },
}

/**
 * 纯淡入动画
 * 仅改变透明度，无位移，持续时间 0.25s
 */
export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: 0.25 },
}

/**
 * 缩放进入动画
 * 元素从 95% 尺寸 + 透明缩放到 100% + 不透明，产生"涌现"效果
 */
export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  transition: { type: 'spring' as const, stiffness: 400, damping: 25 },
}

/**
 * 从右侧滑入动画
 * 元素从屏幕右侧 16px 外滑入，常用于侧栏、菜单等
 */
export const slideInRight = {
  initial: { opacity: 0, x: 16 },
  animate: { opacity: 1, x: 0 },
  transition: { type: 'spring' as const, stiffness: 400, damping: 28 },
}
