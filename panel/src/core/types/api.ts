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
 * 后端 source catalog 的固定分类，与 souwen.models.ALL_SOURCES 保持一致。
 */
export type SourceCategory =
  | 'paper'
  | 'patent'
  | 'general'
  | 'professional'
  | 'social'
  | 'office'
  | 'developer'
  | 'wiki'
  | 'cn_tech'
  | 'video'
  | 'fetch'

export const SOURCE_CATEGORY_ORDER: readonly SourceCategory[] = [
  'paper',
  'patent',
  'general',
  'professional',
  'social',
  'office',
  'developer',
  'wiki',
  'cn_tech',
  'video',
  'fetch',
]

export const SOURCE_CATEGORY_LABEL_KEYS: Record<SourceCategory, string> = {
  paper: 'sources.categoryPaper',
  patent: 'sources.categoryPatent',
  general: 'sources.categoryGeneral',
  professional: 'sources.categoryProfessional',
  social: 'sources.categorySocial',
  office: 'sources.categoryOffice',
  developer: 'sources.categoryDeveloper',
  wiki: 'sources.categoryWiki',
  cn_tech: 'sources.categoryCnTech',
  video: 'sources.categoryVideo',
  fetch: 'sources.categoryFetch',
}

/**
 * 数据源信息（可用性、需要的密钥）
 */
export interface SourceInfo {
  name: string
  needs_key: boolean
  description: string
  key_requirement?: 'none' | 'optional' | 'required' | 'self_hosted'
  auth_requirement?: 'none' | 'optional' | 'required' | 'self_hosted'
  credential_fields?: string[]
  optional_credential_effect?: string | null
  integration_type?: string
  risk_level?: 'low' | 'medium' | 'high'
  risk_reasons?: string[]
  distribution?: 'core' | 'extra' | 'plugin'
  package_extra?: string | null
  stability?: 'stable' | 'beta' | 'experimental' | 'deprecated'
  default_enabled?: boolean
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
  office: SourceInfo[]
  developer: SourceInfo[]
  wiki: SourceInfo[]
  cn_tech: SourceInfo[]
  video: SourceInfo[]
  fetch: SourceInfo[]
}

/**
 * 诊断系统中的数据源信息
 */
export interface DoctorSource {
  name: string
  category: SourceCategory
  status: string
  integration_type: string
  required_key: string | null
  key_requirement: 'none' | 'optional' | 'required' | 'self_hosted'
  auth_requirement?: 'none' | 'optional' | 'required' | 'self_hosted'
  credential_fields?: string[]
  optional_credential_effect?: string | null
  risk_level?: 'low' | 'medium' | 'high'
  risk_reasons?: string[]
  distribution?: 'core' | 'extra' | 'plugin'
  package_extra?: string | null
  stability?: 'stable' | 'beta' | 'experimental' | 'deprecated'
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
  credentials_satisfied?: boolean
  headers: Record<string, string>
  params: Record<string, string | number | boolean>
  category: SourceCategory
  integration_type: string
  key_requirement?: 'none' | 'optional' | 'required' | 'self_hosted'
  auth_requirement?: 'none' | 'optional' | 'required' | 'self_hosted'
  credential_fields?: string[]
  optional_credential_effect?: string | null
  risk_level?: 'low' | 'medium' | 'high'
  risk_reasons?: string[]
  distribution?: 'core' | 'extra' | 'plugin'
  package_extra?: string | null
  stability?: 'stable' | 'beta' | 'experimental' | 'deprecated'
  default_enabled?: boolean
  description: string
}

/**
 * 单个数据源的诊断结果（可达性、延迟、错误信息）
 */
export interface DoctorResult {
  source: string
  category: SourceCategory
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
  available?: number
  degraded?: number
  failed?: number
  limited?: number
  warning?: number
  missing_key?: number
  unavailable?: number
  disabled?: number
  status_counts?: Record<string, number>
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
 * 原始 YAML 配置文件内容响应
 */
export interface YamlConfigResponse {
  content: string
  path: string | null
}

/**
 * Cloudflare Warp 代理状态
 */
export interface WarpStatus {
  status: 'disabled' | 'starting' | 'enabled' | 'stopping' | 'error'
  mode: string
  owner: string
  socks_port: number
  http_port: number
  ip: string
  pid: number
  interface: string | null
  last_error: string
  protocol: string
  proxy_type: string
  available_modes: {
    wireproxy: boolean
    kernel: boolean
    usque: boolean
    'warp-cli': boolean
    external: boolean
  }
}

export interface WarpModeInfo {
  id: string
  name: string
  protocol: string
  installed: boolean
  configured?: boolean
  requires_privilege: boolean
  docker_only: boolean
  proxy_types: string[]
  description: string
  reason?: string
  external_proxy?: string
}

export interface WarpModesResponse {
  modes: WarpModeInfo[]
}

export interface WarpTestResult {
  ok: boolean
  ip: string
  port: number
  mode: string
  protocol: string
}

export interface WarpConfigResponse {
  warp_enabled: boolean
  warp_mode: string
  warp_socks_port: number
  warp_http_port: number
  warp_endpoint: string | null
  warp_bind_address: string
  warp_startup_timeout: number
  warp_device_name: string | null
  warp_usque_transport: string
  warp_external_proxy: string | null
  warp_usque_path: string | null
  warp_usque_config: string | null
  warp_gost_args: string | null
  has_license_key: boolean
  has_team_token: boolean
  has_proxy_auth: boolean
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
 * WARP 组件安装状态
 */
export interface WarpComponentInfo {
  name: string
  installed: boolean
  version: string | null
  path: string | null
  system_path: string | null
  source: 'runtime' | 'system' | 'not_installed'
}

export interface WarpComponentsResponse {
  components: WarpComponentInfo[]
}

export interface WarpInstallResult {
  ok: boolean
  component: string
  version: string
  path: string
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

/* ===== Plugin Management ===== */

/**
 * 插件状态枚举（对齐后端 PluginInfo.status）：
 *   - loaded：当前进程已加载
 *   - available：目录中可用但当前进程未加载，可能需要安装，也可能已安装但待重新扫描/重启
 *   - disabled：已通过 disable 写入禁用列表，重启后跳过
 *   - error：加载失败
 */
export type PluginStatus = 'loaded' | 'available' | 'disabled' | 'error'

/**
 * 插件来源（对齐后端 PluginInfo.source）：
 *   - entry_point：通过 setuptools entry_points 静态目录发现
 *   - catalog：动态目录条目
 *   - config_path：通过 souwen.yaml 的 plugins 字段或 SOUWEN_PLUGINS 环境变量加载
 */
export type PluginSource = 'entry_point' | 'catalog' | 'config_path'

/**
 * 单个插件的状态视图（对齐 src/souwen/plugin_manager.py::PluginInfo）
 */
export interface PluginInfo {
  name: string
  package?: string | null
  version?: string | null
  status: PluginStatus | string
  source: PluginSource | string
  first_party: boolean
  description: string
  error?: string | null
  source_adapters: string[]
  fetch_handlers: string[]
  restart_required: boolean
}

/**
 * GET /api/v1/admin/plugins 响应
 *
 * - plugins：按字典序排列的插件清单
 * - restart_required：服务端是否有任何 enable/disable/install/uninstall 操作未生效，前端用作横幅提示
 * - install_enabled：是否允许 install/uninstall 操作（受 SOUWEN_ENABLE_PLUGIN_INSTALL 控制）
 */
export interface PluginListResponse {
  plugins: PluginInfo[]
  restart_required: boolean
  install_enabled: boolean
}

/**
 * GET /api/v1/admin/plugins/{name}/health 响应
 *
 * 后端透传 `plugin.health_check()` 返回，因此 `status` 之外的字段不固定。
 * 当插件未声明 health_check 时返回 {status: "ok", message: "no health check defined"}。
 */
export interface PluginHealthResponse {
  status: string
  message?: string
  [key: string]: unknown
}

/**
 * POST /api/v1/admin/plugins/{name}/enable 响应
 */
export interface PluginEnableResponse {
  success: boolean
  restart_required: boolean
  message: string
}

/**
 * POST /api/v1/admin/plugins/{name}/disable 响应
 */
export interface PluginDisableResponse {
  success: boolean
  restart_required: boolean
  message: string
}

/**
 * POST /api/v1/admin/plugins/install 与 uninstall 共用响应
 */
export interface PluginInstallResponse {
  success: boolean
  package: string
  restart_required: boolean
  message: string
}

/**
 * POST /api/v1/admin/plugins/reload 响应
 */
export interface PluginReloadResponse {
  loaded: string[]
  errors: { source: string; name: string }[]
  message: string
}
