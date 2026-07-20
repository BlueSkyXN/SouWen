/**
 * 网页抓取页面共享逻辑 Hook
 *
 * 抽取自各皮肤的 FetchPage 组件，包含状态管理、URL 解析、
 * 请求处理、剪贴板操作和文件导出等通用业务逻辑。
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { formatError } from '../lib/errors'
import type { FetchResponse, FetchResult, SourceInfo } from '../types'

export type Provider = string
export type FetchStrategy = 'fallback' | 'fanout'

export interface FetchProviderOption {
  value: Provider
  label: string
  description: string
}

export const DEFAULT_FETCH_PROVIDER_OPTIONS: FetchProviderOption[] = [
  { value: 'builtin', label: 'Builtin', description: 'Built-in fetcher (default)' },
  { value: 'jina_reader', label: 'Jina Reader', description: 'Jina.ai Reader API' },
  { value: 'arxiv_fulltext', label: 'arXiv Fulltext', description: 'arXiv paper fulltext fetcher' },
  { value: 'tavily', label: 'Tavily', description: 'Tavily Extract API' },
  { value: 'firecrawl', label: 'Firecrawl', description: 'Firecrawl scraping service' },
  { value: 'xcrawl', label: 'x-crawl', description: 'x-crawl API' },
  { value: 'exa', label: 'Exa', description: 'Exa.ai content API' },
  { value: 'metaso', label: 'Metaso', description: 'Metaso Reader API' },
  { value: 'kimi_code', label: 'Kimi Code', description: 'Kimi Code fetch API' },
  { value: 'crawl4ai', label: 'Crawl4AI', description: 'Headless browser (local)' },
  { value: 'scrapling', label: 'Scrapling', description: 'Local HTTP/TLS/browser fetcher' },
  { value: 'scrapfly', label: 'Scrapfly', description: 'JS rendering + AI extraction' },
  { value: 'diffbot', label: 'Diffbot', description: 'Structured article extraction' },
  { value: 'scrapingbee', label: 'ScrapingBee', description: 'Proxy + JS rendering + anti-bot' },
  { value: 'zenrows', label: 'ZenRows', description: 'Proxy + JS rendering + anti-bot' },
  { value: 'scraperapi', label: 'ScraperAPI', description: 'Proxy pool + JS rendering' },
  { value: 'apify', label: 'Apify', description: 'Actor-based web crawler platform' },
  { value: 'cloudflare', label: 'Cloudflare', description: 'Edge browser rendering (markdown)' },
  { value: 'wayback', label: 'Wayback Machine', description: 'Internet Archive cached pages (free)' },
  { value: 'newspaper', label: 'Newspaper', description: 'News article extraction (local)' },
  { value: 'readability', label: 'Readability', description: 'Mozilla Readability algorithm (local)' },
  { value: 'mcp', label: 'MCP', description: 'MCP protocol content fetch (external tool)' },
  { value: 'site_crawler', label: 'SiteCrawler', description: 'BFS site crawler (multi-page batch)' },
  { value: 'deepwiki', label: 'DeepWiki', description: 'Open-source project docs (free)' },
]

export const MAX_URLS = 20
const FALLBACK_FETCH_PROVIDER: Provider = 'builtin'
const FETCH_EXTRACT_OPTION_PROVIDERS = new Set<Provider>(['builtin', 'scrapling'])

export const isSafeUrl = (url: string): boolean => /^https?:\/\//i.test(url)

export type FetchState =
  | { status: 'idle'; message: null }
  | { status: 'loading'; message: null }
  | { status: 'error'; message: string }

export function parseUrls(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(isSafeUrl)
}

function humanizeProviderName(name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map((part) => {
      if (part.length <= 3) return part.toUpperCase()
      return part.charAt(0).toUpperCase() + part.slice(1)
    })
    .join(' ')
}

function mergeFetchProviderOptions(sources: SourceInfo[]): FetchProviderOption[] {
  const fallbackByName = new Map(DEFAULT_FETCH_PROVIDER_OPTIONS.map((option) => [option.value, option]))
  const apiFetchSources = sources.filter((source) => source.capabilities.includes('fetch'))
  const apiFetchByName = new Map(apiFetchSources.map((source) => [source.name, source]))
  const apiFetchOptions = apiFetchSources
    .filter((source) => source.available)
    .map((source) => ({
      value: source.name,
      label: fallbackByName.get(source.name)?.label ?? humanizeProviderName(source.name),
      description: source.description || fallbackByName.get(source.name)?.description || source.name,
    }))
  const apiByName = new Map(apiFetchOptions.map((option) => [option.value, option]))
  const ordered = DEFAULT_FETCH_PROVIDER_OPTIONS.flatMap((option) => {
    const apiSource = apiFetchByName.get(option.value)
    if (apiSource && !apiSource.available) return []
    return [apiByName.get(option.value) ?? option]
  })
  const known = new Set(ordered.map((option) => option.value))
  return [
    ...ordered,
    ...apiFetchOptions.filter((option) => !known.has(option.value)),
  ]
}

function providerOptionValues(options: FetchProviderOption[]): Set<Provider> {
  return new Set(options.map((option) => option.value))
}

function normalizeSelectedProviders(
  selectedProviders: Provider[],
  options: FetchProviderOption[],
): Provider[] {
  const validProviders = providerOptionValues(options)
  const normalized = selectedProviders.filter((provider) => validProviders.has(provider))
  if (normalized.length > 0) return normalized
  if (validProviders.has(FALLBACK_FETCH_PROVIDER)) return [FALLBACK_FETCH_PROVIDER]
  return options[0]?.value ? [options[0].value] : [FALLBACK_FETCH_PROVIDER]
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function formatFetchProviderSummary(response: FetchResponse): string {
  const provider = response.provider?.trim()
  if (provider) return provider

  const providers = stringList(response.providers)
  if (providers.length > 0) return providers.join(' + ')

  const requestedProviders = stringList(response.meta?.requested_providers)
  if (requestedProviders.length > 0) return requestedProviders.join(' + ')

  return '—'
}

export function useFetchPage() {
  const { t } = useTranslation()
  const [urls, setUrls] = useState('')
  const [selectedProviders, setSelectedProviders] = useState<Provider[]>(['builtin'])
  const [strategy, setStrategy] = useState<FetchStrategy>('fallback')
  const [timeout, setTimeout_] = useState(30)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selector, setSelector] = useState('')
  const [startIndex, setStartIndex] = useState(0)
  const [maxLength, setMaxLength] = useState<number | undefined>(undefined)
  const [respectRobots, setRespectRobots] = useState(false)
  const [providerOptions, setProviderOptions] = useState<FetchProviderOption[]>(
    DEFAULT_FETCH_PROVIDER_OPTIONS,
  )
  const [fetchState, setFetchState] = useState<FetchState>({ status: 'idle', message: null })
  const [results, setResults] = useState<FetchResponse | null>(null)
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set())
  const addToast = useNotificationStore((s) => s.addToast)
  const activeRequestRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    return () => {
      activeRequestRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api.getSources()
      .then((res) => {
        const nextOptions = mergeFetchProviderOptions(res.sources)
        if (!cancelled) {
          setProviderOptions(nextOptions)
          setSelectedProviders((prev) => normalizeSelectedProviders(prev, nextOptions))
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProviderOptions(DEFAULT_FETCH_PROVIDER_OPTIONS)
          setSelectedProviders((prev) =>
            normalizeSelectedProviders(prev, DEFAULT_FETCH_PROVIDER_OPTIONS),
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const validUrls = parseUrls(urls)
  const canFetch = validUrls.length > 0
  const isLoading = fetchState.status === 'loading'
  const hasResults = results !== null
  const provider = selectedProviders[0] ?? 'builtin'
  const providerSummary = results ? formatFetchProviderSummary(results) : '—'
  const supportsExtractOptions = selectedProviders.some((item) =>
    FETCH_EXTRACT_OPTION_PROVIDERS.has(item),
  )

  const setProvider = useCallback((nextProvider: Provider) => {
    setSelectedProviders((prev) => {
      if (!providerOptionValues(providerOptions).has(nextProvider)) {
        return normalizeSelectedProviders(prev, providerOptions)
      }
      return [nextProvider]
    })
  }, [providerOptions])

  const toggleProvider = useCallback((nextProvider: Provider) => {
    setSelectedProviders((prev) => {
      if (!providerOptionValues(providerOptions).has(nextProvider)) {
        return normalizeSelectedProviders(prev, providerOptions)
      }
      if (prev.includes(nextProvider)) {
        return prev.length === 1 ? prev : prev.filter((item) => item !== nextProvider)
      }
      return [...prev, nextProvider]
    })
  }, [providerOptions])

  const resetAdvancedOptions = useCallback(() => {
    setTimeout_(30)
    setSelectedProviders(normalizeSelectedProviders([FALLBACK_FETCH_PROVIDER], providerOptions))
    setStrategy('fallback')
    setSelector('')
    setStartIndex(0)
    setMaxLength(undefined)
    setRespectRobots(false)
  }, [providerOptions])

  const handleFetch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!canFetch) return

      const urlList = parseUrls(urls)
      if (urlList.length === 0) {
        addToast('error', t('fetch.noValidUrls'))
        return
      }
      if (urlList.length > MAX_URLS) {
        addToast('error', t('fetch.tooManyUrls', { max: MAX_URLS, count: urlList.length }))
        return
      }

      activeRequestRef.current?.abort()
      const controller = new AbortController()
      activeRequestRef.current = controller

      setFetchState({ status: 'loading', message: null })
      setResults(null)
      setExpandedItems(new Set())

      try {
        const fetchOptions = {
          selector: selector || undefined,
          providers: selectedProviders,
          strategy,
          startIndex: startIndex > 0 ? startIndex : undefined,
          maxLength: maxLength,
          respectRobotsTxt: respectRobots || undefined,
        }
        const res = await api.fetch(urlList, provider, timeout, controller.signal, fetchOptions)
        setResults(res)
        setFetchState({ status: 'idle', message: null })
        addToast('success', t('fetch.success', { count: res.total_ok, total: res.total }))
      } catch (err) {
        if (controller.signal.aborted) return
        const message = formatError(err)
        setFetchState({ status: 'error', message })
        addToast('error', t('fetch.failed', { message }))
      } finally {
        if (activeRequestRef.current === controller) {
          activeRequestRef.current = null
        }
      }
    },
    [
      urls,
      provider,
      selectedProviders,
      strategy,
      timeout,
      selector,
      startIndex,
      maxLength,
      respectRobots,
      canFetch,
      addToast,
      t,
    ],
  )

  const handleRetry = useCallback(() => {
    const syntheticEvent = { preventDefault: () => {} } as FormEvent
    handleFetch(syntheticEvent)
  }, [handleFetch])

  const toggleExpanded = useCallback((index: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }, [])

  const copyToClipboard = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text)
        addToast('success', t('fetch.copied'))
      } catch {
        addToast('error', t('fetch.copyFailed'))
      }
    },
    [addToast, t],
  )

  const downloadAsMarkdown = useCallback(
    (item: FetchResult) => {
      const md = `# ${item.title || item.url}\n\n**URL:** ${item.final_url}\n\n${item.content || ''}`
      const blob = new Blob([md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${item.title?.replace(/[\\/:*?"<>|]/g, '_') || 'content'}.md`
      a.click()
      URL.revokeObjectURL(url)
      addToast('success', t('fetch.downloaded'))
    },
    [addToast, t],
  )

  const exportAllAsMarkdown = useCallback(() => {
    if (!results || results.results.length === 0) return
    const md = results.results
      .filter((item) => !item.error)
      .map((item) => `# ${item.title || item.url}\n\n**URL:** ${item.final_url}\n\n${item.content || ''}\n\n---\n`)
      .join('\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'all_content.md'
    a.click()
    URL.revokeObjectURL(url)
    addToast('success', t('fetch.allDownloaded'))
  }, [results, addToast, t])

  return {
    urls,
    setUrls,
    provider,
    setProvider,
    selectedProviders,
    toggleProvider,
    strategy,
    setStrategy,
    providerOptions,
    timeout,
    setTimeout_,
    showAdvanced,
    setShowAdvanced,
    selector,
    setSelector,
    startIndex,
    setStartIndex,
    maxLength,
    setMaxLength,
    respectRobots,
    setRespectRobots,
    supportsExtractOptions,
    resetAdvancedOptions,
    fetchState,
    results,
    providerSummary,
    expandedItems,
    inputRef,
    validUrls,
    canFetch,
    isLoading,
    hasResults,
    handleFetch,
    handleRetry,
    toggleExpanded,
    copyToClipboard,
    downloadAsMarkdown,
    exportAllAsMarkdown,
    t,
  }
}
