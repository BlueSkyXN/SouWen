import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearSearchHistory,
  isFavoriteSearch,
  listFavoriteSearches,
  listSearchHistory,
  recordSearchHistory,
  removeFavoriteSearch,
  searchMemoryId,
  toggleFavoriteSearch,
  type SearchMemoryInput,
} from '../lib/searchMemory'

function input(overrides: Partial<SearchMemoryInput> = {}): SearchMemoryInput {
  return {
    domain: 'paper',
    capability: 'search',
    query: '  graph rag  ',
    sources: ['crossref', 'openalex'],
    resultCount: 3,
    ...overrides,
  }
}

describe('searchMemory', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('records normalized history newest first and deduplicates equivalent searches', () => {
    const first = recordSearchHistory(input(), new Date('2026-01-01T00:00:00Z'))
    const second = recordSearchHistory(
      input({ query: 'graph   rag', sources: ['openalex', 'crossref'] }),
      new Date('2026-01-02T00:00:00Z'),
    )

    expect(first?.id).toBe(second?.id)
    expect(listSearchHistory()).toEqual([
      expect.objectContaining({
        id: first?.id,
        query: 'graph rag',
        sources: ['crossref', 'openalex'],
        createdAt: '2026-01-01T00:00:00.000Z',
        updatedAt: '2026-01-02T00:00:00.000Z',
      }),
    ])
  })

  it('caps history at fifty items', () => {
    for (let i = 0; i < 55; i += 1) {
      recordSearchHistory(input({ query: `query ${i}` }), new Date(`2026-01-01T00:00:${String(i).padStart(2, '0')}Z`))
    }

    const history = listSearchHistory()
    expect(history).toHaveLength(50)
    expect(history[0].query).toBe('query 54')
    expect(history[history.length - 1].query).toBe('query 5')
  })

  it('filters history by domain and capability', () => {
    recordSearchHistory(input({ domain: 'paper', capability: 'search', query: 'paper' }))
    recordSearchHistory(input({ domain: 'web', capability: 'search_news', query: 'news' }))

    expect(listSearchHistory({ domain: 'paper' }).map((item) => item.query)).toEqual(['paper'])
    expect(listSearchHistory({ domain: 'web', capability: 'search_news' }).map((item) => item.query)).toEqual(['news'])

    clearSearchHistory({ domain: 'paper', capability: 'search' })
    expect(listSearchHistory().map((item) => item.query)).toEqual(['news'])
  })

  it('ignores invalid localStorage payloads', () => {
    localStorage.setItem('souwen_search_history_v1', '{bad json')
    localStorage.setItem('souwen_search_favorites_v1', JSON.stringify([{ id: 1 }, input()]))

    expect(listSearchHistory()).toEqual([])
    expect(listFavoriteSearches()).toEqual([])
  })

  it('toggles and removes favorite searches by stable id', () => {
    const favoriteInput = input({ sources: ['openalex', 'crossref', 'openalex'] })
    const id = searchMemoryId(favoriteInput)

    expect(isFavoriteSearch(favoriteInput)).toBe(false)
    const added = toggleFavoriteSearch(favoriteInput, new Date('2026-01-01T00:00:00Z'))
    expect(added?.id).toBe(id)
    expect(isFavoriteSearch(favoriteInput)).toBe(true)
    expect(listFavoriteSearches()).toEqual([
      expect.objectContaining({ id, query: 'graph rag', sources: ['crossref', 'openalex'] }),
    ])

    expect(toggleFavoriteSearch(favoriteInput)).toBeNull()
    expect(listFavoriteSearches()).toEqual([])

    toggleFavoriteSearch(favoriteInput)
    removeFavoriteSearch(id)
    expect(listFavoriteSearches()).toEqual([])
  })

  it('does not persist empty queries or empty source selections', () => {
    expect(recordSearchHistory(input({ query: '  ' }))).toBeNull()
    expect(toggleFavoriteSearch(input({ sources: [] }))).toBeNull()
    expect(listSearchHistory()).toEqual([])
    expect(listFavoriteSearches()).toEqual([])

    clearSearchHistory()
    expect(listSearchHistory()).toEqual([])
  })
})
