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
  id: 'souwen-classic',
  labelKey: 'skin.classic',
  descriptionKey: 'skin.classicDesc',
  defaultScheme: 'nebula',
  schemes: [
    { id: 'nebula', labelKey: 'theme.nebula', dotColor: '#4f46e5' },
    { id: 'aurora', labelKey: 'theme.aurora', dotColor: '#0d9488' },
    { id: 'obsidian', labelKey: 'theme.obsidian', dotColor: '#475569' },
  ],
}
