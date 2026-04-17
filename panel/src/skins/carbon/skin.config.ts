/**
 * 文件用途：Carbon 皮肤的设计令牌和主题配置，定义该皮肤的标识、默认模式、可用配色方案等
 *
 * 配置清单：
 *   skinConfig（SkinConfig 类型对象）
 *     - id: 'carbon' - 皮肤的唯一标识符
 *     - labelKey: 'skin.carbon' - 国际化标签 key
 *     - descriptionKey: 'skin.carbonDesc' - 国际化描述 key
 *     - defaultScheme: 'terminal' - 默认配色方案 ID（需在 schemes 数组中定义）
 *     - defaultMode: 'dark' - 默认主题模式为深色（Carbon 风格）
 *     - schemes: 可用配色方案数组：
 *       terminal（蓝色 #3b82f6）、matrix（绿色 #10b981）、ember（橙色 #f59e0b）
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
 * Carbon 皮肤的配置对象
 * 定义了该皮肤的基本属性和可用的主题方案（三种配色：Terminal、Matrix、Ember）
 * 该配置会在皮肤启动时被应用到应用全局
 */
export const skinConfig: SkinConfig = {
  id: 'carbon',
  labelKey: 'skin.carbon',
  descriptionKey: 'skin.carbonDesc',
  defaultScheme: 'terminal',
  defaultMode: 'light',
  // 该皮肤支持的配色方案列表
  schemes: [
    {
      id: 'terminal',
      labelKey: 'theme.terminal',
      dotColor: '#3b82f6', // 终端蓝色
    },
    {
      id: 'matrix',
      labelKey: 'theme.matrix',
      dotColor: '#10b981', // 矩阵绿色
    },
    {
      id: 'ember',
      labelKey: 'theme.ember',
      dotColor: '#f59e0b', // 余烬橙色
    },
  ],
}
