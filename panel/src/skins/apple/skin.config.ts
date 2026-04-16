import type { SkinConfig } from '@core/types'

export const skinConfig: SkinConfig = {
  id: 'apple',
  labelKey: 'skin.apple',
  descriptionKey: 'skin.appleDesc',
  defaultScheme: 'blue',
  defaultMode: 'light',
  schemes: [
    { id: 'blue', labelKey: 'theme.appleBlue', dotColor: '#0071e3' },
  ],
}
