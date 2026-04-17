/**
 * Skin 配置文件 - souwen-classic 皮肤配置
 *
 * 文件用途：定义 souwen-classic 皮肤的元数据、默认主题设置和可用配色方案
 *
 * SkinConfig 结构：
 *   - id (string): 皮肤唯一标识符
 *   - labelKey (string): i18n 国际化标签键
 *   - descriptionKey (string): i18n 国际化描述键
 *   - defaultScheme (string): 默认配色方案 ID
 *   - defaultMode (string): 默认显示模式（light/dark）
 *   - schemes (SkinScheme[]): 可用配色方案列表
 *     - id (string): 方案唯一标识符
 *     - labelKey (string): i18n 标签键
 *     - dotColor (string): 主题选择器中的颜色点示意
 */

import type { SkinConfig } from '@core/types'

export const skinConfig: SkinConfig = {
  id: 'souwen-classic',
  labelKey: 'skin.classic',
  descriptionKey: 'skin.classicDesc',
  defaultScheme: 'nebula',
  defaultMode: 'light',
  // 三种配色方案：星云蓝、极光青、黑曜石灰
  schemes: [
    { id: 'nebula', labelKey: 'theme.nebula', dotColor: '#4f46e5' },
    { id: 'aurora', labelKey: 'theme.aurora', dotColor: '#0d9488' },
    { id: 'obsidian', labelKey: 'theme.obsidian', dotColor: '#475569' },
  ],
}
