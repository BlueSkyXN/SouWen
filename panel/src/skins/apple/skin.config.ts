/**
 * 文件用途：Apple 皮肤的设计令牌和主题配置，定义该皮肤的标识、默认模式、可用配色方案等
 *
 * 配置清单：
 *   skinConfig（SkinConfig 类型对象）
 *     - id: 'apple' - 皮肤的唯一标识符
 *     - labelKey: 'skin.apple' - 国际化标签 key，用于显示皮肤名称
 *     - descriptionKey: 'skin.appleDesc' - 国际化描述 key，用于显示皮肤简介
 *     - defaultScheme: 'blue' - 默认配色方案 ID（需在 schemes 数组中定义）
 *     - defaultMode: 'light' - 默认主题模式（'light' | 'dark'）
 *     - schemes: 可用配色方案数组，每项包含 id、labelKey、dotColor
 *
 * 设计令牌说明：
 *   schemes[].id - 配色方案的标识符，与 CSS 变量的 data-scheme 属性对应
 *   schemes[].labelKey - 该方案在 UI 中显示的名称
 *   schemes[].dotColor - 该方案在皮肤选择器中显示的颜色圆点，用于视觉识别
 *
 * 模块依赖：
 *   - @core/types: SkinConfig 类型定义
 */

import type { SkinConfig } from '@core/types'

/**
 * Apple 皮肤的配置对象
 * 定义了该皮肤的基本属性和可用的主题方案
 * 该配置会在皮肤启动时被应用到应用全局
 */
export const skinConfig: SkinConfig = {
  id: 'apple',
  labelKey: 'skin.apple',
  descriptionKey: 'skin.appleDesc',
  defaultScheme: 'blue',
  defaultMode: 'light',
  // 该皮肤支持的配色方案列表
  schemes: [
    {
      id: 'blue',
      labelKey: 'theme.appleBlue',
      dotColor: '#0071e3', // Apple 品牌蓝色
    },
  ],
}
