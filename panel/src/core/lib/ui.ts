import type { TFunction } from 'i18next'

type BadgeColor = 'blue' | 'amber' | 'green' | 'red'

export function categoryBadgeColor(category: string): BadgeColor {
  switch (category) {
    case 'paper': return 'blue'
    case 'patent': return 'amber'
    case 'web': return 'green'
    default: return 'blue'
  }
}

export function tierBadgeColor(tier: number): BadgeColor {
  switch (tier) {
    case 0: return 'green'
    case 1: return 'blue'
    default: return 'amber'
  }
}

export function categoryLabel(t: TFunction, category: string): string {
  return t(`dashboard.${category}`, category)
}
