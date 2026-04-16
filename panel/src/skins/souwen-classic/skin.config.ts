import type { SkinConfig } from '@core/types'

export const skinConfig: SkinConfig = {
  id: 'souwen-classic',
  labelKey: 'skin.classic',
  descriptionKey: 'skin.classicDesc',
  defaultScheme: 'nebula',
  defaultMode: 'light',
  schemes: [
    { id: 'nebula', labelKey: 'theme.nebula', dotColor: '#4f46e5' },
    { id: 'aurora', labelKey: 'theme.aurora', dotColor: '#0d9488' },
    { id: 'obsidian', labelKey: 'theme.obsidian', dotColor: '#475569' },
  ],
}
