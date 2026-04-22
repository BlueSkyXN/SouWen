/**
 * 文件用途：API 响应类型定义，与后端 src/souwen/models.py 保持对齐
 *
 * 类型分组：
 *   - 通用 API 响应：HealthResponse / SourceInfo / SourcesResponse / ConfigResponse / ReloadResponse
 *   - 诊断与配置：DoctorSource / DoctorResult / DoctorResponse / SourceChannelConfig
 *   - 网络代理：WarpStatus / WarpActionResult / HttpBackendResponse
 *   - 搜索结果：Author / Applicant / PaperResult / PatentResult / WebResult
 *                SearchSourceResult / SearchResponse / WebSearchResponse
 *   - 多媒体搜索：ImageResult / ImageSearchResponse / VideoResult / VideoSearchResponse
 *   - YouTube：YouTubeVideoDetail / YouTubeTrendingResponse / YouTubeVideoDetailResponse
 *              TranscriptSegment / YouTubeTranscriptResponse
 *   - Wayback Machine：WaybackSnapshot / WaybackCDXResponse / WaybackAvailabilityResponse / WaybackSaveResponse
 *   - 内容抓取：FetchResult / FetchResponse
 *   - 链接 / Sitemap：LinkItem / LinkExtractionResult / SitemapEntry / SitemapResult
 *
 * 该文件由 panel/src/core/types/index.ts 通过 `export *` 透传，外部仍可从 '@core/types' 直接导入。
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
  key_requirement: 'none' | 'optional' | 'required' | 'self_hosted'
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
  engines: string[]
  results: WebResult[]
  total: number
  meta: SearchMeta
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

// === Bilibili ===
// 注：除聚合搜索（/api/v1/search/web?engine=bilibili）外，后端还暴露 /api/v1/bilibili/* 直连接口，
// 这里给出对应的响应结构。

export interface BilibiliSearchItem {
  bvid: string
  aid?: number
  title: string
  author: string
  mid?: number
  play: number
  danmaku: number
  favorites?: number
  description: string
  duration: string
  pic: string
  pubdate?: number
  tag?: string
  type?: string
}

export interface BilibiliSearchResponse {
  keyword: string
  results: BilibiliSearchItem[]
  total: number
  page: number
  page_size?: number
  order?: string
}

export interface BilibiliVideoDetail {
  bvid: string
  aid?: number
  title: string
  description?: string
  pic: string
  duration?: number | string
  pubdate?: number
  owner?: { mid?: number; name?: string; face?: string }
  stat?: {
    view?: number
    danmaku?: number
    reply?: number
    favorite?: number
    coin?: number
    share?: number
    like?: number
  }
  tags?: string[]
  [key: string]: unknown
}

export interface BilibiliVideoDetailResponse {
  bvid: string
  data: BilibiliVideoDetail
}

export interface BilibiliUserItem {
  mid: number
  uname: string
  usign?: string
  fans?: number
  videos?: number
  upic?: string
  level?: number
  [key: string]: unknown
}

export interface BilibiliArticleItem {
  id: number
  title: string
  author?: string
  view?: number
  like?: number
  description?: string
  image_urls?: string[]
  [key: string]: unknown
}

export interface BilibiliUserSearchResponse {
  keyword: string
  results: BilibiliUserItem[]
  total: number
  page: number
}

export interface BilibiliArticleSearchResponse {
  keyword: string
  results: BilibiliArticleItem[]
  total: number
  page: number
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

/**
 * 链接提取 — 单个链接项
 */
export interface LinkItem {
  url: string
  text: string
}

/**
 * 链接提取响应
 */
export interface LinkExtractionResult {
  source_url: string
  final_url: string
  links: LinkItem[]
  total: number
  filtered_count: number
  error: string | null
}

/**
 * Sitemap 条目
 */
export interface SitemapEntry {
  loc: string
  lastmod: string | null
  changefreq: string | null
  priority: number | null
}

/**
 * Sitemap 解析响应
 */
export interface SitemapResult {
  root_url: string
  entries: SitemapEntry[]
  total: number
  sitemaps_parsed: number
  errors: string[]
}

/* ===== Auth / Whoami ===== */

/**
 * 角色枚举（与后端 Role IntEnum 对齐）
 */
export type UserRole = 'guest' | 'user' | 'admin'

/**
 * /api/v1/whoami 响应
 */
export interface WhoamiResponse {
  role: UserRole
  features: Record<string, boolean | string>
  guest_enabled: boolean
}
