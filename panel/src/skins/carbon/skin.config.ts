export interface SchemeDefinition {
  id: string
  labelKey: string
  dotColor: string
}

export interface SkinConfig {
  id: string
  labelKey: string
  descriptionKey: string
  defaultScheme: string
  schemes: SchemeDefinition[]
}

export const skinConfig: SkinConfig = {
  id: 'carbon',
  labelKey: 'skin.carbon',
  descriptionKey: 'skin.carbonDesc',
  defaultScheme: 'terminal',
  schemes: [
    { id: 'terminal', labelKey: 'theme.terminal', dotColor: '#3b82f6' },
    { id: 'matrix', labelKey: 'theme.matrix', dotColor: '#10b981' },
    { id: 'ember', labelKey: 'theme.ember', dotColor: '#f59e0b' },
  ],
}
