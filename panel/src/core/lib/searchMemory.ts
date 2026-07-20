export interface SearchMemoryInput {
  domain: string
  capability: string
  query: string
  sources: string[]
  resultCount?: number
}

export interface SearchMemoryItem extends SearchMemoryInput {
  id: string
  createdAt: string
  updatedAt: string
}

export interface SearchMemoryFilter {
  domain?: string
  capability?: string
}

const HISTORY_KEY = 'souwen_search_history_v1'
const FAVORITES_KEY = 'souwen_search_favorites_v1'
const MAX_HISTORY_ITEMS = 50

function storageAvailable(): boolean {
  return typeof localStorage !== 'undefined'
}

function normalizeQuery(query: string): string {
  return query.trim().replace(/\s+/g, ' ')
}

function normalizeSources(sources: string[]): string[] {
  return Array.from(new Set(sources.map((source) => source.trim()).filter(Boolean))).sort()
}

function stableHash(value: string): string {
  let hash = 5381
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(i)
  }
  return (hash >>> 0).toString(36)
}

function normalizeInput(input: SearchMemoryInput): SearchMemoryInput {
  return {
    ...input,
    query: normalizeQuery(input.query),
    sources: normalizeSources(input.sources),
  }
}

export function searchMemoryId(input: SearchMemoryInput): string {
  const normalized = normalizeInput(input)
  return stableHash([
    normalized.domain,
    normalized.capability,
    normalized.query.toLowerCase(),
    normalized.sources.join(','),
  ].join('\u001f'))
}

function isSearchMemoryItem(value: unknown): value is SearchMemoryItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return (
    typeof item.id === 'string'
    && typeof item.domain === 'string'
    && typeof item.capability === 'string'
    && typeof item.query === 'string'
    && Array.isArray(item.sources)
    && item.sources.every((source) => typeof source === 'string')
    && typeof item.createdAt === 'string'
    && typeof item.updatedAt === 'string'
    && (item.resultCount === undefined || typeof item.resultCount === 'number')
  )
}

function readItems(key: string): SearchMemoryItem[] {
  if (!storageAvailable()) return []
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isSearchMemoryItem)
  } catch {
    return []
  }
}

function writeItems(key: string, items: SearchMemoryItem[]): void {
  if (!storageAvailable()) return
  localStorage.setItem(key, JSON.stringify(items))
}

function matchesFilter(item: SearchMemoryItem, filter?: SearchMemoryFilter): boolean {
  if (!filter) return true
  if (filter.domain && item.domain !== filter.domain) return false
  if (filter.capability && item.capability !== filter.capability) return false
  return true
}

function makeItem(input: SearchMemoryInput, now: Date, existing?: SearchMemoryItem): SearchMemoryItem {
  const normalized = normalizeInput(input)
  const id = searchMemoryId(normalized)
  const timestamp = now.toISOString()
  return {
    ...normalized,
    id,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
  }
}

export function listSearchHistory(filter?: SearchMemoryFilter): SearchMemoryItem[] {
  return readItems(HISTORY_KEY).filter((item) => matchesFilter(item, filter))
}

export function listFavoriteSearches(filter?: SearchMemoryFilter): SearchMemoryItem[] {
  return readItems(FAVORITES_KEY).filter((item) => matchesFilter(item, filter))
}

export function recordSearchHistory(input: SearchMemoryInput, now = new Date()): SearchMemoryItem | null {
  const normalized = normalizeInput(input)
  if (!normalized.query || normalized.sources.length === 0) return null

  const id = searchMemoryId(normalized)
  const current = readItems(HISTORY_KEY)
  const existing = current.find((item) => item.id === id)
  const nextItem = makeItem(normalized, now, existing)
  const next = [nextItem, ...current.filter((item) => item.id !== id)].slice(0, MAX_HISTORY_ITEMS)
  writeItems(HISTORY_KEY, next)
  return nextItem
}

export function clearSearchHistory(filter?: SearchMemoryFilter): void {
  if (!storageAvailable()) return
  if (!filter) {
    localStorage.removeItem(HISTORY_KEY)
    return
  }
  writeItems(HISTORY_KEY, readItems(HISTORY_KEY).filter((item) => !matchesFilter(item, filter)))
}

export function isFavoriteSearch(input: SearchMemoryInput): boolean {
  const id = searchMemoryId(input)
  return readItems(FAVORITES_KEY).some((item) => item.id === id)
}

export function toggleFavoriteSearch(input: SearchMemoryInput, now = new Date()): SearchMemoryItem | null {
  const normalized = normalizeInput(input)
  if (!normalized.query || normalized.sources.length === 0) return null

  const id = searchMemoryId(normalized)
  const current = readItems(FAVORITES_KEY)
  const existing = current.find((item) => item.id === id)
  if (existing) {
    writeItems(FAVORITES_KEY, current.filter((item) => item.id !== id))
    return null
  }

  const nextItem = makeItem(normalized, now)
  writeItems(FAVORITES_KEY, [nextItem, ...current])
  return nextItem
}

export function removeFavoriteSearch(id: string): void {
  writeItems(FAVORITES_KEY, readItems(FAVORITES_KEY).filter((item) => item.id !== id))
}
