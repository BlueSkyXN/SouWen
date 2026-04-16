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
