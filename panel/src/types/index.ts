/* ===== API Response Types ===== */

export interface HealthResponse {
  status: string
  version: string
}

export interface SourceInfo {
  name: string
  needs_key: string | null
  description: string
}

export interface SourcesResponse {
  paper: SourceInfo[]
  patent: SourceInfo[]
  web: SourceInfo[]
}

export interface DoctorSource {
  name: string
  category: string
  status: string
  tier: number
  required_key: string | null
  message: string
}

export interface DoctorResponse {
  total: number
  ok: number
  sources: DoctorSource[]
}

export interface ConfigResponse {
  [key: string]: unknown
}

export interface ReloadResponse {
  status: string
  password_set: boolean
}

/* ===== Search Types ===== */

export interface PaperResult {
  title: string
  authors?: string[]
  year?: number
  doi?: string
  abstract?: string
  url?: string
  source?: string
}

export interface PatentResult {
  title: string
  patent_number?: string
  assignee?: string
  date?: string
  abstract?: string
  url?: string
  source?: string
}

export interface WebResult {
  title: string
  url: string
  snippet?: string
  engine?: string
}

export interface SearchSourceResult {
  source: string
  results: (PaperResult | PatentResult | WebResult)[]
  error?: string
}

export interface SearchResponse {
  query: string
  sources?: string[]
  results: SearchSourceResult[]
  total: number
}

export interface WebSearchResponse {
  query: string
  engines: string[]
  results: WebResult[]
  total: number
}

/* ===== UI Types ===== */

export type Theme = 'light' | 'dark'

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
}

export type SearchCategory = 'paper' | 'patent' | 'web'
