/**
 * 文件用途：iOS 皮肤的配置和设计令牌定义
 * 包括皮肤标识、默认主题模式/配色方案、色彩令牌和排版设置
 * 采用 iOS HIG 设计规范，提供现代化的视觉体验
 */

import type { SkinConfig } from '@core/types'

export const skinConfig: SkinConfig = {
  id: 'ios',
  labelKey: 'skin.ios',
  descriptionKey: 'skin.iosDesc',
  defaultScheme: 'default',
  defaultMode: 'light',
  schemes: [
    { id: 'default', labelKey: 'theme.iosDefault', dotColor: '#007aff' },
  ],
}
