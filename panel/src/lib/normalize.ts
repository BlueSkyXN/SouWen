import type { PaperResult, PatentResult, WebResult, DoctorSource } from '../types'

export interface NormalizedPaper {
  title: string
  authors: string[]
  year: number | null
  doi: string
  abstract: string
  url: string
  source: string
  citationCount: number | null
  pdfUrl: string
}

export interface NormalizedPatent {
  title: string
  patentNumber: string
  applicant: string
  inventors: string[]
  abstract: string
  url: string
  source: string
  publicationDate: string
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
  const authors = Array.isArray(raw.authors)
    ? raw.authors
        .map((a) => (typeof a === 'string' ? a : a?.name ?? ''))
        .filter(Boolean)
    : []
  return {
    title: raw.title?.trim() || '',
    authors,
    year: typeof raw.year === 'number' ? raw.year : null,
    doi: raw.doi?.trim() || '',
    abstract: raw.abstract?.trim() || '',
    url: raw.source_url?.trim() || raw.open_access_url?.trim() || '',
    source: typeof raw.source === 'string' ? raw.source : '',
    citationCount: typeof raw.citation_count === 'number' ? raw.citation_count : null,
    pdfUrl: raw.pdf_url?.trim() || '',
  }
}

export function normalizePatent(raw: PatentResult): NormalizedPatent {
  const applicant = Array.isArray(raw.applicants) && raw.applicants.length > 0
    ? raw.applicants.map((a) => (typeof a === 'string' ? a : a?.name ?? '')).filter(Boolean).join(', ')
    : ''
  return {
    title: raw.title?.trim() || '',
    patentNumber: raw.patent_id?.trim() || '',
    applicant,
    inventors: Array.isArray(raw.inventors) ? raw.inventors.filter(Boolean) : [],
    abstract: raw.abstract?.trim() || '',
    url: raw.source_url?.trim() || '',
    source: typeof raw.source === 'string' ? raw.source : '',
    publicationDate: raw.publication_date?.trim() || '',
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
