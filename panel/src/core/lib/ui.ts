/**
 * 文件用途：UI 工具库，提供搜索结果分类与等级的徽章颜色映射
 *
 * 类型/函数清单：
 *     BadgeColor（类型别名）
 *         - 定义：'blue' | 'amber' | 'green' | 'red'
 *         - 用途：徽章组件支持的颜色值
 *
 *     categoryBadgeColor(category: string) -> BadgeColor
 *         - 功能：根据搜索结果分类返回对应的徽章颜色
 *         - 逻辑：
 *           - paper → blue（蓝色，代表学术、正式）
 *           - patent → amber（琥珀色，代表知识产权）
 *           - web → green（绿色，代表互联网、通用）
 *           - 其他 → blue（默认）
 *
 *     tierBadgeColor(tier: number) -> BadgeColor
 *         - 功能：根据数据源优先级等级返回对应的徽章颜色
 *         - 逻辑：
 *           - tier 0 → green（最高优先级，绿色突出）
 *           - tier 1 → blue（中等优先级）
 *           - tier ≥ 2 → amber（较低优先级，琥珀色示警）
 *
 *     categoryLabel(t: TFunction, category: string) -> string
 *         - 功能：使用 i18next 获取分类的本地化标签
 *         - 输入：t i18next 翻译函数，category 分类名
 *         - 输出：本地化标签文本（中文）
 *         - 逻辑：调用 t(`dashboard.${category}`) 获取翻译，回退为原始分类名
 *
 * 模块依赖：
 *     - i18next: TFunction 类型定义
 */

import type { TFunction } from 'i18next'

/**
 * 徽章颜色类型
 */
type BadgeColor = 'blue' | 'amber' | 'green' | 'red'

/**
 * 根据搜索结果分类获取徽章颜色
 * paper 蓝色、patent 琥珀色、web 绿色
 */
export function categoryBadgeColor(category: string): BadgeColor {
  switch (category) {
    case 'paper': return 'blue'
    case 'patent': return 'amber'
    case 'web': return 'green'
    default: return 'blue'
  }
}

/**
 * 根据数据源等级获取徽章颜色
 * tier 0（最高）绿色、tier 1 蓝色、tier ≥2 琥珀色
 */
export function tierBadgeColor(tier: number): BadgeColor {
  switch (tier) {
    case 0: return 'green'
    case 1: return 'blue'
    default: return 'amber'
  }
}

/**
 * 获取分类的本地化标签
 * 调用 i18n 获取中文标签（如果无翻译则返回原分类名）
 */
export function categoryLabel(t: TFunction, category: string): string {
  return t(`dashboard.${category}`, category)
}
