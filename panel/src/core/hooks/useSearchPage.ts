/**
 * useSearchPage — 通用搜索页 Hook
 *
 * 提供统一的搜索状态管理；具体派发由调用者实现。各皮肤的 SearchPage 视图直接使用本 hook。
 *
 * 契约示例：
 *   const { query, setQuery, loading, error, handleSearch } = useSearchPage('paper')
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../services/api'
import {
  clearSearchHistory,
  isFavoriteSearch,
  listFavoriteSearches,
  listSearchHistory,
  recordSearchHistory,
  removeFavoriteSearch,
  toggleFavoriteSearch,
  type SearchMemoryItem,
} from '../lib/searchMemory'
import type {
  ImageSearchResponse,
  SearchResponse,
  SourceInfo,
  VideoSearchResponse,
  WebSearchResponse,
} from '../types'

export const SEARCH_CAPABILITIES = [
  'search',
  'search_news',
  'search_images',
  'search_videos',
  'search_articles',
  'search_users',
  'get_detail',
  'get_trending',
  'get_transcript',
  'fetch',
  'archive_lookup',
  'archive_save',
] as const

export type Capability = typeof SEARCH_CAPABILITIES[number]

export const SEARCH_DOMAINS = [
  'book',
  'paper',
  'patent',
  'web',
  'social',
  'video',
  'knowledge',
  'developer',
  'cn_tech',
  'office',
  'archive',
] as const

export type Domain = typeof SEARCH_DOMAINS[number]

export interface SearchPageState {
  domain: string
  capability: Capability
  setCapability: (c: Capability) => void
  query: string
  setQuery: (q: string) => void
  availableSources: SourceInfo[]
  selectedSources: string[]
  toggleSource: (name: string) => void
  setSelectedSources: (names: string[]) => void
  results: unknown[]
  responses: SearchPageResponse[]
  loading: boolean
  error: { message: string } | null
  handleSearch: () => Promise<void>
  supportedCapabilities: Capability[]
  searchHistory: SearchMemoryItem[]
  favoriteSearches: SearchMemoryItem[]
  canFavoriteCurrentSearch: boolean
  isCurrentFavorite: boolean
  applySearchMemory: (item: SearchMemoryItem) => void
  toggleCurrentFavorite: () => void
  removeFavoriteSearch: (id: string) => void
  clearCurrentSearchHistory: () => void
}

export type SearchPageResponse =
  | SearchResponse
  | WebSearchResponse
  | ImageSearchResponse
  | VideoSearchResponse

/** Domain → 支持的 capabilities 列表 */
const DOMAIN_CAPABILITIES: Record<Domain, Capability[]> = {
  book: ['search'],
  paper: ['search'],
  patent: ['search'],
  web: ['search', 'search_news', 'search_images', 'search_videos'],
  social: ['search'],
  video: ['search'],
  knowledge: ['search'],
  developer: ['search'],
  cn_tech: ['search'],
  office: ['search'],
  archive: ['archive_lookup'],
}
const DEFAULT_CAPABILITIES: Capability[] = ['search']

function capabilitiesForDomain(domain: string): Capability[] {
  return DOMAIN_CAPABILITIES[domain as Domain] ?? DEFAULT_CAPABILITIES
}

export function useSearchPage(domain: string): SearchPageState {
  const supportedCapabilities = capabilitiesForDomain(domain)

  const [query, setQuery] = useState('')
  const [capability, setCapability] = useState<Capability>(supportedCapabilities[0])
  const [availableSources, setAvailableSources] = useState<SourceInfo[]>([])
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [results, setResults] = useState<unknown[]>([])
  const [responses, setResponses] = useState<SearchPageResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ message: string } | null>(null)
  const [searchHistory, setSearchHistory] = useState<SearchMemoryItem[]>([])
  const [favoriteSearches, setFavoriteSearches] = useState<SearchMemoryItem[]>([])

  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)

  const refreshSearchMemory = useCallback(() => {
    const filter = { domain, capability }
    setSearchHistory(listSearchHistory(filter))
    setFavoriteSearches(listFavoriteSearches(filter))
  }, [domain, capability])

  useEffect(() => {
    refreshSearchMemory()
  }, [refreshSearchMemory])

  const currentSearchInput = useMemo(() => ({
    domain,
    capability,
    query,
    sources: selectedSources,
  }), [domain, capability, query, selectedSources])

  const canFavoriteCurrentSearch = query.trim().length > 0 && selectedSources.length > 0
  const isCurrentFavorite = canFavoriteCurrentSearch && isFavoriteSearch(currentSearchInput)

  // 拉取当前 domain / capability 可用源
  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const data = await api.getSources()
        if (!mounted) return
        const activeCapability = supportedCapabilities.includes(capability) ? capability : supportedCapabilities[0]
        const defaultKey = `${domain}:${activeCapability}`
        const defaults = new Set(data.defaults?.[defaultKey] ?? [])
        const sources = data.sources
          .filter((source) =>
            source.domain === domain
            && source.available
            && source.capabilities.includes(activeCapability),
          )
        const defaultNames = sources
          .filter((source) => defaults.has(source.name) || source.default_for.includes(defaultKey))
          .map((source) => source.name)
        setAvailableSources(sources)
        // domain / capability 切换时重置选择，避免残留上一个筛选范围的源名
        setSelectedSources(defaultNames.length > 0 ? defaultNames : sources.map((source: SourceInfo) => source.name))
      } catch {
        // silently fail; UI can fall back
      }
    })()
    return () => {
      mounted = false
    }
  }, [domain, capability, supportedCapabilities])

  useEffect(() => {
    const caps = capabilitiesForDomain(domain)
    if (!caps.includes(capability)) {
      setCapability(caps[0])
    }
  }, [domain, capability])

  const toggleSource = useCallback((name: string) => {
    setSelectedSources((prev: string[]) =>
      prev.includes(name) ? prev.filter((n: string) => n !== name) : [...prev, name],
    )
  }, [])

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim()
    if (!trimmed || selectedSources.length === 0) return

    const reqId = ++requestIdRef.current
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const sourcesCSV = selectedSources.join(',')

    setLoading(true)
    setError(null)

    try {
      let resp: SearchPageResponse | SearchPageResponse[]
      if (domain === 'book') {
        resp = (await api.searchBook(trimmed, sourcesCSV, 10, controller.signal)) as SearchResponse
      } else if (domain === 'paper') {
        resp = (await api.searchPaper(trimmed, sourcesCSV, 10, controller.signal)) as SearchResponse
      } else if (domain === 'patent') {
        resp = (await api.searchPatent(trimmed, sourcesCSV, 10, controller.signal)) as SearchResponse
      } else if (domain === 'web' && capability === 'search_news') {
        resp = (await api.searchNews(
          trimmed,
          10,
          'wt-wt',
          'moderate',
          undefined,
          controller.signal,
          undefined,
          sourcesCSV,
        )) as WebSearchResponse
      } else if (domain === 'web' && capability === 'search_images') {
        resp = (await api.searchImages(
          trimmed,
          10,
          'wt-wt',
          'moderate',
          controller.signal,
          undefined,
          sourcesCSV,
        )) as ImageSearchResponse
      } else if (domain === 'web' && capability === 'search_videos') {
        resp = (await api.searchVideos(
          trimmed,
          10,
          'wt-wt',
          'moderate',
          controller.signal,
          undefined,
          sourcesCSV,
        )) as VideoSearchResponse
      } else {
        resp = (await api.searchWeb(trimmed, sourcesCSV, 10, controller.signal)) as WebSearchResponse
      }
      if (reqId !== requestIdRef.current) return

      const respList = Array.isArray(resp) ? resp : [resp]
      setResponses(respList)
      const allResults: unknown[] = respList.flatMap((r) => (r?.results ?? []) as unknown[])
      setResults(allResults)
      recordSearchHistory({
        domain,
        capability,
        query: trimmed,
        sources: selectedSources,
        resultCount: respList.reduce((sum, r) => sum + (typeof r.total === 'number' ? r.total : 0), 0),
      })
      refreshSearchMemory()
    } catch (e: unknown) {
      if (reqId !== requestIdRef.current) return
      if ((e as { name?: string })?.name === 'AbortError') return
      setError({ message: (e as Error)?.message || String(e) })
    } finally {
      if (reqId === requestIdRef.current) setLoading(false)
    }
  }, [query, selectedSources, domain, capability, refreshSearchMemory])

  const applySearchMemory = useCallback((item: SearchMemoryItem) => {
    if (item.domain !== domain) return
    if (supportedCapabilities.includes(item.capability as Capability)) {
      setCapability(item.capability as Capability)
    }
    setQuery(item.query)
    const availableSourceNames = new Set(availableSources.map((source) => source.name))
    setSelectedSources(item.sources.filter((source) => availableSourceNames.has(source)))
  }, [domain, supportedCapabilities, availableSources])

  const toggleCurrentFavorite = useCallback(() => {
    toggleFavoriteSearch(currentSearchInput)
    refreshSearchMemory()
  }, [currentSearchInput, refreshSearchMemory])

  const removeFavoriteById = useCallback((id: string) => {
    removeFavoriteSearch(id)
    refreshSearchMemory()
  }, [refreshSearchMemory])

  const clearCurrentSearchHistory = useCallback(() => {
    clearSearchHistory({ domain, capability })
    refreshSearchMemory()
  }, [domain, capability, refreshSearchMemory])

  return {
    domain,
    capability,
    setCapability,
    query,
    setQuery,
    availableSources,
    selectedSources,
    toggleSource,
    setSelectedSources,
    results,
    responses,
    loading,
    error,
    handleSearch,
    supportedCapabilities,
    searchHistory,
    favoriteSearches,
    canFavoriteCurrentSearch,
    isCurrentFavorite,
    applySearchMemory,
    toggleCurrentFavorite,
    removeFavoriteSearch: removeFavoriteById,
    clearCurrentSearchHistory,
  }
}
