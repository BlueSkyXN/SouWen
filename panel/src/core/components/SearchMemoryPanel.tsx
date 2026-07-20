import { Clock3, Star, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SearchMemoryItem } from '../lib/searchMemory'

interface SearchMemoryPanelClasses {
  root: string
  header: string
  title: string
  actions: string
  actionButton: string
  groups: string
  group: string
  groupTitle: string
  chips: string
  chip: string
  chipText: string
  chipMeta: string
  removeButton: string
  empty: string
}

interface SearchMemoryPanelProps {
  history: SearchMemoryItem[]
  favorites: SearchMemoryItem[]
  isCurrentFavorite: boolean
  canFavorite: boolean
  onApply: (item: SearchMemoryItem) => void
  onToggleCurrentFavorite: () => void
  onRemoveFavorite: (id: string) => void
  onClearHistory: () => void
  classes: SearchMemoryPanelClasses
}

function summarizeSources(sources: string[]): string {
  if (sources.length <= 2) return sources.join(', ')
  return `${sources.slice(0, 2).join(', ')} +${sources.length - 2}`
}

function formatMeta(item: SearchMemoryItem): string {
  const sources = summarizeSources(item.sources)
  if (typeof item.resultCount !== 'number') return sources
  return `${sources} · ${item.resultCount}`
}

export function SearchMemoryPanel({
  history,
  favorites,
  isCurrentFavorite,
  canFavorite,
  onApply,
  onToggleCurrentFavorite,
  onRemoveFavorite,
  onClearHistory,
  classes,
}: SearchMemoryPanelProps) {
  const { t } = useTranslation()
  const hasContent = history.length > 0 || favorites.length > 0 || canFavorite

  if (!hasContent) return null

  const renderItems = (items: SearchMemoryItem[], type: 'history' | 'favorite') => {
    if (items.length === 0) {
      return <div className={classes.empty}>{t(type === 'history' ? 'search.noHistory' : 'search.noFavorites')}</div>
    }

    return (
      <div className={classes.chips}>
        {items.slice(0, 6).map((item) => (
          <span key={item.id} className={classes.chip}>
            <button
              type="button"
              className={classes.chipText}
              onClick={() => onApply(item)}
              title={`${item.query} · ${item.sources.join(', ')}`}
              aria-label={t('search.reuseSearch', { query: item.query })}
            >
              {item.query}
              <span className={classes.chipMeta}>{formatMeta(item)}</span>
            </button>
            {type === 'favorite' && (
              <button
                type="button"
                className={classes.removeButton}
                onClick={() => onRemoveFavorite(item.id)}
                aria-label={t('search.removeFavorite')}
                title={t('search.removeFavorite')}
              >
                <X size={13} />
              </button>
            )}
          </span>
        ))}
      </div>
    )
  }

  return (
    <section className={classes.root} aria-label={t('search.memory')}>
      <div className={classes.header}>
        <div className={classes.title}>
          <Clock3 size={15} />
          {t('search.memory')}
        </div>
        <div className={classes.actions}>
          <button
            type="button"
            className={classes.actionButton}
            onClick={onToggleCurrentFavorite}
            disabled={!canFavorite}
            aria-pressed={isCurrentFavorite}
          >
            <Star size={13} fill={isCurrentFavorite ? 'currentColor' : 'none'} />
            {isCurrentFavorite ? t('search.unfavoriteCurrent') : t('search.favoriteCurrent')}
          </button>
          {history.length > 0 && (
            <button type="button" className={classes.actionButton} onClick={onClearHistory}>
              <Trash2 size={13} />
              {t('search.clearHistory')}
            </button>
          )}
        </div>
      </div>
      <div className={classes.groups}>
        <div className={classes.group}>
          <div className={classes.groupTitle}>{t('search.favorites')}</div>
          {renderItems(favorites, 'favorite')}
        </div>
        <div className={classes.group}>
          <div className={classes.groupTitle}>{t('search.history')}</div>
          {renderItems(history, 'history')}
        </div>
      </div>
    </section>
  )
}
