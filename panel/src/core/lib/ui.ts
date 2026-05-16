/**
 * 文件用途：UI 工具库，提供搜索结果分类与集成类型的徽章颜色映射
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
 *     integrationBadgeColor(integration_type: string) -> BadgeColor
 *         - 功能：根据数据源集成类型返回对应的徽章颜色
 *         - 逻辑：
 *           - open_api → green（公开接口，绿色突出）
 *           - scraper → amber（爬虫抓取，琥珀色示警）
 *           - official_api → blue（授权接口，蓝色）
 *           - self_hosted → red（自托管，红色）
 *           - 其他 → blue（默认）
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
import { SOURCE_CATEGORY_LABEL_KEYS, SOURCE_CATEGORY_ORDER } from '../types'
import type { SourceCategory } from '../types'

/**
 * 徽章颜色类型
 */
type BadgeColor = 'blue' | 'amber' | 'green' | 'red' | 'indigo' | 'teal'

/**
 * 根据搜索结果分类获取徽章颜色
 */
export function categoryBadgeColor(category: string): BadgeColor {
  switch (category) {
    case 'paper': return 'blue'
    case 'patent': return 'amber'
    case 'web_general': return 'green'
    case 'web_professional': return 'indigo'
    case 'social': return 'amber'
    case 'office': return 'teal'
    case 'developer': return 'green'
    case 'knowledge': return 'blue'
    case 'cn_tech': return 'teal'
    case 'video': return 'red'
    case 'archive': return 'amber'
    case 'fetch': return 'amber'
    default: return 'blue'
  }
}

/**
 * 根据数据源集成类型获取徽章颜色
 * open_api 绿色、scraper 琥珀色、official_api 蓝色、self_hosted 红色
 */
export function integrationBadgeColor(integration_type: string): BadgeColor {
  switch (integration_type) {
    case 'open_api': return 'green'
    case 'scraper': return 'amber'
    case 'official_api': return 'blue'
    case 'self_hosted': return 'red'
    default: return 'blue'
  }
}

/**
 * Type guard：判断给定字符串是否是合法的 SourceCategory
 */
function isSourceCategory(value: string): value is SourceCategory {
  return (SOURCE_CATEGORY_ORDER as readonly string[]).includes(value)
}

/**
 * 获取分类的本地化标签
 * 调用 i18n 获取中文标签（如果无翻译则返回原分类名）
 */
export function categoryLabel(t: TFunction, category: string): string {
  const key = isSourceCategory(category)
    ? SOURCE_CATEGORY_LABEL_KEYS[category]
    : `dashboard.${category}`
  return t(key, category)
}
