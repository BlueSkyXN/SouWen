import type { SkinConfig } from '@core/types'

export const skinConfig: SkinConfig = {
  id: 'carbon',
  labelKey: 'skin.carbon',
  descriptionKey: 'skin.carbonDesc',
  defaultScheme: 'terminal',
  defaultMode: 'dark',
  schemes: [
    { id: 'terminal', labelKey: 'theme.terminal', dotColor: '#3b82f6' },
    { id: 'matrix', labelKey: 'theme.matrix', dotColor: '#10b981' },
    { id: 'ember', labelKey: 'theme.ember', dotColor: '#f59e0b' },
  ],
}
