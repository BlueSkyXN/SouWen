/**
 * 工具箱页面共享逻辑 Hook
 *
 * 抽取自各皮肤的 ToolsPage 组件，包含 Wayback Machine 相关的
 * 三类操作（CDX 快照查询、可用性检测、提交存档）的状态管理与请求处理。
 */

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { hasFeatureAccess } from '../lib/access'
import { useNotificationStore } from '../stores/notificationStore'
import { useAuthStore } from '../stores/authStore'
import type {
  WaybackSnapshot,
  WaybackAvailabilityResponse,
  WaybackSaveResponse,
} from '../types'

export type Tab = 'cdx' | 'check' | 'save'

export function formatWaybackTimestamp(ts: string): string {
  if (!ts || ts.length < 8) return ts
  const yyyy = ts.slice(0, 4)
  const mm = ts.slice(4, 6)
  const dd = ts.slice(6, 8)
  const hh = ts.length >= 10 ? ts.slice(8, 10) : '00'
  const mi = ts.length >= 12 ? ts.slice(10, 12) : '00'
  const ss = ts.length >= 14 ? ts.slice(12, 14) : '00'
  try {
    const d = new Date(`${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}Z`)
    if (isNaN(d.getTime())) return ts
    return d.toLocaleString()
  } catch {
    return ts
  }
}

export function snapshotViewUrl(url: string, timestamp: string): string {
  return `https://web.archive.org/web/${timestamp}/${url}`
}

function toWaybackDate(s: string): string | undefined {
  const trimmed = s.trim()
  if (!trimmed) return undefined
  return trimmed.replace(/-/g, '')
}

export function useToolsPage() {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const features = useAuthStore((s) => s.features)
  const role = useAuthStore((s) => s.role)
  const canSave = hasFeatureAccess(features, role, 'wayback_save')
  const [tab, setTab] = useState<Tab>('cdx')
  const abortRef = useRef<AbortController | null>(null)

  // CDX state
  const [cdxUrl, setCdxUrl] = useState('')
  const [cdxFrom, setCdxFrom] = useState('')
  const [cdxTo, setCdxTo] = useState('')
  const [cdxLimit, setCdxLimit] = useState(50)
  const [cdxLoading, setCdxLoading] = useState(false)
  const [cdxResults, setCdxResults] = useState<WaybackSnapshot[]>([])

  // Check state
  const [checkUrl, setCheckUrl] = useState('')
  const [checkLoading, setCheckLoading] = useState(false)
  const [checkResult, setCheckResult] = useState<WaybackAvailabilityResponse | null>(null)

  // Save state
  const [saveUrl, setSaveUrl] = useState('')
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveResult, setSaveResult] = useState<WaybackSaveResponse | null>(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  useEffect(() => {
    if (!canSave && tab === 'save') setTab('cdx')
  }, [canSave, tab])

  const cancelInflight = () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    return abortRef.current.signal
  }

  const handleCdxQuery = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!cdxUrl.trim()) return
    const signal = cancelInflight()
    setCdxLoading(true)
    setCdxResults([])
    try {
      const res = await api.waybackCDX(
        cdxUrl.trim(),
        {
          from: toWaybackDate(cdxFrom),
          to: toWaybackDate(cdxTo),
          limit: cdxLimit,
        },
        signal,
      )
      setCdxResults(res.snapshots ?? [])
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setCdxLoading(false)
    }
  }

  const handleCheck = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!checkUrl.trim()) return
    const signal = cancelInflight()
    setCheckLoading(true)
    setCheckResult(null)
    try {
      const res = await api.waybackCheck(checkUrl.trim(), undefined, signal)
      setCheckResult(res)
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setCheckLoading(false)
    }
  }

  const handleSave = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!canSave) return
    if (!saveUrl.trim()) return
    const signal = cancelInflight()
    setSaveLoading(true)
    setSaveResult(null)
    try {
      const res = await api.waybackSave(saveUrl.trim(), 60, signal)
      setSaveResult(res)
      if (res.success) {
        addToast('success', t('tools.saveSuccess'))
      } else {
        addToast('error', res.error || t('tools.saveFailed'))
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        addToast('error', err.message)
      }
    } finally {
      setSaveLoading(false)
    }
  }

  return {
    t,
    tab,
    setTab,
    // cdx
    cdxUrl, setCdxUrl,
    cdxFrom, setCdxFrom,
    cdxTo, setCdxTo,
    cdxLimit, setCdxLimit,
    cdxLoading,
    cdxResults,
    handleCdxQuery,
    // check
    checkUrl, setCheckUrl,
    checkLoading,
    checkResult,
    handleCheck,
    // save
    canSave,
    saveUrl, setSaveUrl,
    saveLoading,
    saveResult,
    handleSave,
  }
}
