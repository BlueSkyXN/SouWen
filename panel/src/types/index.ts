/* ===== API Response Types ===== */

export interface HealthResponse {
  status: string
  version: string
}

export interface SourceInfo {
  name: string
  needs_key: boolean
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

export interface DoctorResult {
  source: string
  category: string
  tier: number
  reachable: boolean
  latency_ms?: number
  error?: string
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

export interface WarpStatus {
  status: 'disabled' | 'starting' | 'enabled' | 'stopping' | 'error'
  mode: string
  owner: string
  socks_port: number
  ip: string
  pid: number
  interface: string | null
  last_error: string
  available_modes: {
    wireproxy: boolean
    kernel: boolean
  }
}

export interface WarpActionResult {
  ok: boolean
  mode?: string
  ip?: string
  message?: string
  error?: string
}

/* ===== Search Types (aligned with backend models.py) ===== */

export interface Author {
  name: string
  affiliation?: string | null
  orcid?: string | null
}

export interface Applicant {
  name: string
  country?: string | null
}

export interface PaperResult {
  source: string
  title: string
  authors: Author[]
  abstract?: string | null
  doi?: string | null
  year?: number | null
  publication_date?: string | null
  journal?: string | null
  venue?: string | null
  citation_count?: number | null
  open_access_url?: string | null
  pdf_url?: string | null
  source_url: string
  tldr?: string | null
  raw?: Record<string, unknown>
}

export interface PatentResult {
  source: string
  title: string
  patent_id: string
  application_number?: string | null
  publication_date?: string | null
  filing_date?: string | null
  applicants: Applicant[]
  inventors: string[]
  abstract?: string | null
  claims?: string | null
  ipc_codes: string[]
  cpc_codes: string[]
  family_id?: string | null
  legal_status?: string | null
  pdf_url?: string | null
  source_url: string
  raw?: Record<string, unknown>
}

export interface WebResult {
  source: string
  title: string
  url: string
  snippet: string
  engine: string
  raw?: Record<string, unknown>
}

export interface SearchSourceResult {
  query: string
  source: string
  total_results?: number | null
  results: (PaperResult | PatentResult | WebResult)[]
  page?: number
  per_page?: number
}

export interface SearchResponse {
  query: string
  sources: string[]
  results: SearchSourceResult[]
  total: number
}

export interface WebSearchResponse {
  query: string
  source: string
  total_results: number
  results: WebResult[]
  page: number
  per_page: number
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
