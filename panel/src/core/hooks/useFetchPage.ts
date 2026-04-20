/**
 * 网页抓取页面共享逻辑 Hook
 *
 * 抽取自 4 个皮肤的 FetchPage 组件，包含状态管理、URL 解析、
 * 请求处理、剪贴板操作和文件导出等通用业务逻辑。
 */

import { useState, useCallback, useEffect, useRef, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import { formatError } from '../lib/errors'
import type { FetchResponse, FetchResult } from '../types'

export type Provider = 'builtin' | 'jina_reader' | 'tavily' | 'firecrawl' | 'exa'

export const MAX_URLS = 20

export const isSafeUrl = (url: string): boolean => /^https?:\/\//i.test(url)

export type FetchState =
  | { status: 'idle'; message: null }
  | { status: 'loading'; message: null }
  | { status: 'error'; message: string }

export function parseUrls(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && (line.startsWith('http://') || line.startsWith('https://')))
}

export function useFetchPage() {
  const { t } = useTranslation()
  const [urls, setUrls] = useState('')
  const [provider, setProvider] = useState<Provider>('builtin')
  const [timeout, setTimeout_] = useState(30)
  const [showAdvanced, setShowAdvanced] = useState(false)
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

  const validUrls = parseUrls(urls)
  const canFetch = validUrls.length > 0
  const isLoading = fetchState.status === 'loading'
  const hasResults = results !== null

  const handleFetch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      if (!canFetch) return

      const urlList = parseUrls(urls)
      if (urlList.length === 0) {
        addToast('error', t('fetch.noValidUrls', 'No valid URLs found'))
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
        const res = await api.fetch(urlList, provider, timeout, controller.signal)
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
    [urls, provider, timeout, canFetch, addToast, t],
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
        addToast('success', t('fetch.copied', 'Copied to clipboard'))
      } catch {
        addToast('error', t('fetch.copyFailed', 'Failed to copy'))
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
      addToast('success', t('fetch.downloaded', 'Downloaded as Markdown'))
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
    addToast('success', t('fetch.allDownloaded', 'All content downloaded'))
  }, [results, addToast, t])

  return {
    urls,
    setUrls,
    provider,
    setProvider,
    timeout,
    setTimeout_,
    showAdvanced,
    setShowAdvanced,
    fetchState,
    results,
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
