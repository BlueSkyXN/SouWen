import type { PaperResult, PatentResult, WebResult, DoctorSource } from '../types'

export interface NormalizedPaper {
  title: string
  authors: string[]
  year: number | null
  doi: string
  abstract: string
  url: string
  source: string
}

export interface NormalizedPatent {
  title: string
  patentNumber: string
  applicant: string
  abstract: string
  url: string
  source: string
}

export interface NormalizedWeb {
  title: string
  url: string
  snippet: string
  source: string
}

export interface NormalizedSource {
  name: string
  type: 'paper' | 'patent' | 'web'
  tier: number
  reachable: boolean
  error: string | null
}

export function normalizePaper(raw: PaperResult): NormalizedPaper {
  return {
    title: raw.title?.trim() || '',
    authors: Array.isArray(raw.authors) ? raw.authors.filter(Boolean) : [],
    year: typeof raw.year === 'number' ? raw.year : null,
    doi: raw.doi?.trim() || '',
    abstract: raw.abstract?.trim() || '',
    url: raw.url?.trim() || '',
    source: raw.source || '',
  }
}

export function normalizePatent(raw: PatentResult): NormalizedPatent {
  return {
    title: raw.title?.trim() || '',
    patentNumber: raw.patent_number?.trim() || '',
    applicant: raw.assignee?.trim() || '',
    abstract: raw.abstract?.trim() || '',
    url: raw.url?.trim() || '',
    source: raw.source || '',
  }
}

export function normalizeWeb(raw: WebResult): NormalizedWeb {
  return {
    title: raw.title?.trim() || '',
    url: raw.url?.trim() || '',
    snippet: raw.snippet?.trim() || '',
    source: raw.engine || '',
  }
}

export function normalizeDoctor(raw: DoctorSource): NormalizedSource {
  return {
    name: raw.name || '',
    type: (raw.category as NormalizedSource['type']) || 'paper',
    tier: typeof raw.tier === 'number' ? raw.tier : 2,
    reachable: raw.status === 'ok',
    error: raw.status !== 'ok' ? raw.message || null : null,
  }
}

export function tierLabel(tier: number): string {
  switch (tier) {
    case 0: return 'Tier 0'
    case 1: return 'Tier 1'
    case 2: return 'Tier 2'
    default: return `Tier ${tier}`
  }
}

export function typeLabel(type: string): string {
  switch (type) {
    case 'paper': return '论文'
    case 'patent': return '专利'
    case 'web': return '网页'
    default: return type
  }
}
