/**
 * useSearchPage — 通用搜索页 Hook
 *
 * 提供统一的搜索状态管理；具体派发由调用者实现。各皮肤的 SearchPage 视图直接使用本 hook。
 *
 * 契约示例：
 *   const { query, setQuery, loading, error, handleSearch } = useSearchPage('paper')
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../services/api'
import type { SearchResponse, SourceInfo, WebSearchResponse } from '../types'

export type Capability =
  | 'search'
  | 'search_news'
  | 'search_images'
  | 'search_videos'
  | 'search_articles'
  | 'search_users'
  | 'get_detail'
  | 'get_trending'
  | 'get_transcript'
  | 'fetch'
  | 'archive_lookup'
  | 'archive_save'

export type Domain =
  | 'paper' | 'patent' | 'web' | 'social' | 'video'
  | 'knowledge' | 'developer' | 'cn_tech' | 'office' | 'archive'

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
  responses: Array<SearchResponse | WebSearchResponse>
  loading: boolean
  error: { message: string } | null
  handleSearch: () => Promise<void>
  supportedCapabilities: Capability[]
}

/** Domain → 支持的 capabilities 列表 */
const DOMAIN_CAPABILITIES: Record<string, Capability[]> = {
  paper: ['search'],
  patent: ['search'],
  web: ['search', 'search_news', 'search_images', 'search_videos'],
  social: ['search'],
  video: ['search', 'get_trending'],
  knowledge: ['search'],
  developer: ['search'],
  cn_tech: ['search'],
  office: ['search'],
  archive: ['archive_lookup'],
}
const DEFAULT_CAPABILITIES: Capability[] = ['search']

export function useSearchPage(domain: string): SearchPageState {
  const supportedCapabilities = DOMAIN_CAPABILITIES[domain] ?? DEFAULT_CAPABILITIES

  const [query, setQuery] = useState('')
  const [capability, setCapability] = useState<Capability>(supportedCapabilities[0])
  const [availableSources, setAvailableSources] = useState<SourceInfo[]>([])
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [results, setResults] = useState<unknown[]>([])
  const [responses, setResponses] = useState<Array<SearchResponse | WebSearchResponse>>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ message: string } | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)

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
    const caps = DOMAIN_CAPABILITIES[domain] ?? ['search']
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
      let resp: SearchResponse | WebSearchResponse | SearchResponse[]
      if (domain === 'paper') {
        resp = (await api.searchPaper(trimmed, sourcesCSV, 10, controller.signal)) as SearchResponse
      } else if (domain === 'patent') {
        resp = (await api.searchPatent(trimmed, sourcesCSV, 10, controller.signal)) as SearchResponse
      } else {
        resp = (await api.searchWeb(trimmed, sourcesCSV, 10, controller.signal)) as WebSearchResponse
      }
      if (reqId !== requestIdRef.current) return

      const respList = Array.isArray(resp) ? resp : [resp]
      setResponses(respList as Array<SearchResponse | WebSearchResponse>)
      const allResults: unknown[] = respList.flatMap((r) => (r?.results ?? []) as unknown[])
      setResults(allResults)
    } catch (e: unknown) {
      if (reqId !== requestIdRef.current) return
      if ((e as { name?: string })?.name === 'AbortError') return
      setError({ message: (e as Error)?.message || String(e) })
    } finally {
      if (reqId === requestIdRef.current) setLoading(false)
    }
  }, [query, selectedSources, domain])

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
  }
}
