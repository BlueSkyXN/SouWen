/**
 * 文件用途：核心类型定义文件，定义 API 响应格式、搜索结果、UI 组件、皮肤系统等 TypeScript 接口
 *
 * 类型分组清单：
 *
 * === API 响应类型 ===
 *     HealthResponse: 服务健康检查响应（status, version）
 *     SourceInfo: 数据源信息（名称、是否需密钥、描述）
 *     SourcesResponse: 按分类列出可用数据源（paper[], patent[], web[]）
 *     DoctorSource: 诊断系统数据源项（状态、优先级、错误信息）
 *     SourceChannelConfig: 数据源完整配置（启用状态、代理、API 密钥、自定义参数）
 *     DoctorResult: 诊断结果项（可达性、延迟、错误）
 *     DoctorResponse: 诊断系统响应（汇总统计与详细信息）
 *     ConfigResponse: 系统配置响应（字典形式）
 *     ReloadResponse: 配置重载响应（密码设置状态）
 *     WarpStatus: Cloudflare Warp 代理状态（启用/禁用/错误，IP 信息，SOCKS 端口）
 *     WarpActionResult: Warp 操作结果（成功/失败及详情）
 *     HttpBackendResponse: HTTP 代理后端配置（默认/覆盖规则，curl-cffi 可用性）
 *
 * === 搜索结果类型 ===
 *     Author: 论文作者对象（名字、隶属机构、ORCID）
 *     Applicant: 专利申请人对象（名字、国家）
 *     PaperResult: 论文搜索结果（标题、作者、DOI、引用数、PDF 链接等）
 *     PatentResult: 专利搜索结果（专利号、申请人、IPC/CPC 编码、法律状态等）
 *     WebResult: 网页搜索结果（标题、URL、摘要、搜索引擎）
 *     SearchSourceResult: 单个数据源的搜索结果（包含分页、结果总数）
 *     SearchResponse: 聚合搜索响应（跨多个源的统一结果）
 *     WebSearchResponse: 网页搜索响应（含分页信息）
 *
 * === UI 类型 ===
 *     Theme: 明暗主题（'light' | 'dark'）
 *     VisualTheme: 皮肤配色方案 ID（如 'nebula', 'terminal' 等，由每个皮肤定义）
 *     ToastType: 通知类型（'success' | 'error' | 'info'）
 *     Toast: 通知对象（ID、类型、消息）
 *     SearchCategory: 搜索分类（'paper' | 'patent' | 'general' | 'professional' | 'social' | 'developer' | 'wiki' | 'video'）
 *
 * === 皮肤系统类型 ===
 *     SchemeDefinition: 配色方案定义（ID、标签 i18n 键、点颜色用于选择器）
 *     SkinConfig: 皮肤元数据（ID、标签、默认方案/主题、所有可用方案）
 *     SkinState: 皮肤状态（当前主题/方案、切换函数、加载函数）
 *     SkinModule: 皮肤模块接口（导出 React 组件、路由、配置、引导函数）
 *
 * 模块依赖：
 *     - React: 用于 React.ComponentType 类型
 */

/* ===== API Response Types ===== */

/**
 * 服务健康检查响应
 */
export interface HealthResponse {
  status: string
  version: string
}

/**
 * 数据源信息（可用性、需要的密钥）
 */
export interface SourceInfo {
  name: string
  needs_key: boolean
  description: string
}

/**
 * 按分类返回可用数据源列表
 */
export interface SourcesResponse {
  paper: SourceInfo[]
  patent: SourceInfo[]
  general: SourceInfo[]
  professional: SourceInfo[]
  social: SourceInfo[]
  developer: SourceInfo[]
  wiki: SourceInfo[]
  video: SourceInfo[]
  fetch: SourceInfo[]
}

/**
 * 诊断系统中的数据源信息
 */
export interface DoctorSource {
  name: string
  category: string
  status: string
  integration_type: string
  required_key: string | null
  message: string
  enabled: boolean
  description?: string
  channel?: Record<string, string> | null
}

/**
 * 数据源的完整配置（含代理、HTTP 后端、API 密钥等）
 */
export interface SourceChannelConfig {
  enabled: boolean
  proxy: string
  http_backend: string
  base_url: string | null
  has_api_key: boolean
  headers: Record<string, string>
  params: Record<string, string | number | boolean>
  category: string
  integration_type: string
  description: string
}

/**
 * 单个数据源的诊断结果（可达性、延迟、错误信息）
 */
export interface DoctorResult {
  source: string
  category: string
  integration_type: string
  reachable: boolean
  latency_ms?: number
  error?: string
}

/**
 * 完整诊断系统响应
 */
export interface DoctorResponse {
  total: number
  ok: number
  sources: DoctorSource[]
}

/**
 * 系统配置响应（通用字典）
 */
export interface ConfigResponse {
  [key: string]: unknown
}

/**
 * 配置重载响应
 */
export interface ReloadResponse {
  status: string
  password_set: boolean
}

/**
 * Cloudflare Warp 代理状态
 */
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

/**
 * Warp 操作（启用/禁用）的结果
 */
export interface WarpActionResult {
  ok: boolean
  mode?: string
  ip?: string
  message?: string
  error?: string
}

/**
 * HTTP 代理后端配置
 */
export interface HttpBackendResponse {
  default: string
  overrides: Record<string, string>
  curl_cffi_available: boolean
}

/* ===== Search Types (aligned with backend models.py) ===== */

/**
 * 论文作者对象
 */
export interface Author {
  name: string
  affiliation?: string | null
  orcid?: string | null
}

/**
 * 专利申请人对象
 */
export interface Applicant {
  name: string
  country?: string | null
}

/**
 * 论文搜索结果
 */
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

/**
 * 专利搜索结果
 */
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

/**
 * 网页搜索结果
 */
export interface WebResult {
  source: string
  title: string
  url: string
  snippet: string
  engine: string
  raw?: Record<string, unknown>
}

/**
 * 单个数据源的搜索结果（含分页）
 */
export interface SearchSourceResult {
  query: string
  source: string
  total_results?: number | null
  results: (PaperResult | PatentResult | WebResult)[]
  page?: number
  per_page?: number
}

/**
 * 聚合搜索响应（跨多个源）
 */
export interface SearchResponse {
  query: string
  sources: string[]
  results: SearchSourceResult[]
  total: number
}

/**
 * 网页搜索响应
 */
export interface WebSearchResponse {
  query: string
  source: string
  total_results: number
  results: WebResult[]
  page: number
  per_page: number
}

/**
 * 通用搜索元数据（图片/视频搜索响应中的 meta 字段）
 */
export interface SearchMeta {
  [key: string]: unknown
}

// === 图片搜索 ===
export interface ImageResult {
  source: string
  title: string
  url: string
  image_url: string
  thumbnail_url: string
  width: number
  height: number
  image_source: string
  engine: string
}

export interface ImageSearchResponse {
  query: string
  results: ImageResult[]
  total: number
  meta: SearchMeta
}

// === 视频搜索 ===
export interface VideoResult {
  source: string
  title: string
  url: string
  duration: string
  publisher: string
  published: string
  description: string
  thumbnail: string
  embed_url: string
  view_count: number
  engine: string
}

export interface VideoSearchResponse {
  query: string
  results: VideoResult[]
  total: number
  meta: SearchMeta
}

// === YouTube ===
export interface YouTubeVideoDetail {
  video_id: string
  title: string
  description: string
  channel_title: string
  channel_id: string
  published_at: string
  duration_seconds: number
  view_count: number
  like_count: number
  comment_count: number
  thumbnail_url: string
  tags: string[]
  category_id: string
}

export interface YouTubeTrendingResponse {
  region: string
  category: string
  results: YouTubeVideoDetail[]
  total: number
}

export interface YouTubeVideoDetailResponse {
  video_ids: string[]
  results: YouTubeVideoDetail[]
  total: number
}

export interface TranscriptSegment {
  text: string
  start: number
  duration: number
}

export interface YouTubeTranscriptResponse {
  video_id: string
  lang: string
  segments: TranscriptSegment[]
  available: boolean
}

// === Wayback Machine ===
export interface WaybackSnapshot {
  url: string
  timestamp: string
  status_code: number
  mime_type: string
  length: number
  digest: string
}

export interface WaybackCDXResponse {
  url: string
  snapshots: WaybackSnapshot[]
  total: number
}

export interface WaybackAvailabilityResponse {
  url: string
  available: boolean
  snapshot_url: string | null
  timestamp: string | null
  status: number | null
}

export interface WaybackSaveResponse {
  url: string
  success: boolean
  snapshot_url: string | null
  timestamp: string | null
  error: string | null
}

/**
 * 网页内容抓取结果（单个 URL）
 */
export interface FetchResult {
  url: string
  final_url: string
  title?: string
  content?: string
  content_format?: string
  snippet?: string
  source: string
  published_date?: string
  author?: string
  error?: string
  raw?: Record<string, unknown>
}

/**
 * 网页内容抓取响应（批量）
 */
export interface FetchResponse {
  urls: string[]
  results: FetchResult[]
  total: number
  total_ok: number
  total_failed: number
  provider: string
  meta?: Record<string, unknown>
}

/* ===== UI Types ===== */

/**
 * 应用主题：明亮或深色
 */
export type Theme = 'light' | 'dark'

/**
 * 皮肤配色方案 ID
 * 每个皮肤可定义多个方案（如 nebula/aurora/obsidian），用户可切换
 */
export type VisualTheme = string

/**
 * 通知/Toast 类型
 */
export type ToastType = 'success' | 'error' | 'info'

/**
 * 通知对象
 */
export interface Toast {
  id: string
  type: ToastType
  message: string
}

/**
 * 搜索分类
 */
export type SearchCategory = 'paper' | 'patent' | 'general' | 'professional' | 'social' | 'developer' | 'wiki' | 'video'

/** Web-derived categories that use /api/v1/search/web endpoint */
export const WEB_CATEGORIES: ReadonlySet<SearchCategory> = new Set([
  'general', 'professional', 'social', 'developer', 'wiki', 'video',
])

/** All search categories in display order */
export const ALL_CATEGORIES: readonly SearchCategory[] = [
  'paper', 'patent', 'general', 'professional', 'social', 'developer', 'wiki', 'video',
]

/* ===== Skin System Types ===== */

/**
 * 皮肤配色方案定义
 * 每个方案对应一套配色（如深蓝、浅紫等）
 */
export interface SchemeDefinition {
  id: string
  labelKey: string
  dotColor: string
}

/**
 * 皮肤元数据和配置
 * 定义皮肤的标识、支持的方案、默认主题
 */
export interface SkinConfig {
  id: string
  labelKey: string
  descriptionKey: string
  defaultScheme: string
  defaultMode: Theme
  schemes: SchemeDefinition[]
}

/**
 * 皮肤运行时状态
 * 跟踪当前的主题和配色方案选择
 */
export interface SkinState {
  mode: Theme
  scheme: string
  toggleMode: () => void
  setScheme: (s: string) => void
  loadSkin: () => void
}

/**
 * 皮肤模块接口
 * 一个皮肤的完整导出：UI 组件、路由、配置、初始化函数
 */
export interface SkinModule {
  AppShell: React.ComponentType
  LoginPage: React.ComponentType
  skinRoutes: React.ReactNode
  skinConfig: SkinConfig
  ErrorBoundary: React.ComponentType<{ children: React.ReactNode }>
  ToastContainer: React.ComponentType
  Spinner: React.ComponentType<{ size?: 'sm' | 'md' | 'lg' }>
  bootstrap: () => void
}
