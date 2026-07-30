/* Generated from contracts/openapi/souwen-openapi-2.0.0rc5.json; do not edit. */
/* generator_version=2 */
/* openapi_sha256=27308a32af13e16f3e05cb7e3a19e6547cd389340df8aa3ac976b1829b1198bb */

export const SDK_VERSION = '2.0.0rc5' as const
export const SUPPORTED_API_MAJOR = 2 as const
export const OPENAPI_SHA256 = '27308a32af13e16f3e05cb7e3a19e6547cd389340df8aa3ac976b1829b1198bb' as const
export const DEFAULT_TIMEOUT_MS = 125_000
export const SEARCH_DOMAINS = ["paper", "book", "research_output", "patent", "web", "news", "images", "videos", "social", "office", "developer", "cn_tech", "knowledge"] as const
export type SearchDomain = typeof SEARCH_DOMAINS[number]

export interface ClientRequestContext {
  request_id?: string | null
  trace_id?: string | null
}

export interface ContentMetadata {
  charset?: string | null
  content_length?: number | null
  media_type: string
  quality?: "high" | "low" | null
  retrieved_at?: string | null
  truncated: boolean
}

export interface ErrorDetail {
  code: "invalid_request" | "unauthenticated" | "forbidden" | "not_found" | "conflict" | "api_major_mismatch" | "rate_limited" | "payload_too_large" | "unsupported_media_type" | "worker_unavailable" | "worker_not_ready" | "worker_overloaded" | "worker_timeout" | "worker_protocol_mismatch" | "provider_timeout" | "provider_unavailable" | "policy_blocked" | "internal_error"
  message: string
  provider?: string | null
  request_id: string
  retryable: boolean
}

export interface ErrorResponse {
  context: RequestContext
  error: ErrorDetail
}

export interface EvidenceItem {
  id: string
  item_id: string
  provider: string
  public_url: string
  retrieved_at: string
  title_or_snippet: string
}

export interface FetchBatch {
  context: RequestContext
  items: Array<FetchResult>
  meta: FetchMeta
}

export interface FetchContentOptions {
  max_code_points?: number | null
}

export interface FetchMeta {
  partial?: boolean
}

export interface FetchPolicyOptions {
  respect_robots?: true | null
}

export interface FetchRequest {
  content?: FetchContentOptions | null
  policy?: FetchPolicyOptions | null
  providers?: Array<ProviderRef> | null
  strategy?: "fallback" | "fanout" | null
  targets: Array<string>
}

export interface FetchResult {
  content?: string | null
  content_metadata?: ContentMetadata | null
  error?: ErrorDetail | null
  final_url?: string | null
  provenance: Array<Provenance>
  status: "success" | "failed" | "blocked"
  target: string
  title?: string | null
}

export interface HTTPValidationError {
  detail?: Array<ValidationError>
}

export interface LLMFetchOptions {
  enabled?: boolean
}

export interface LLMSearchBudget {
  max_attempts?: number | null
  timeout_seconds?: number | null
}

export interface LLMSearchRequest {
  budget?: LLMSearchBudget | null
  fetch?: LLMFetchOptions | null
  max_results_per_provider?: number | null
  providers: Array<ProviderRef>
  query: string
  strategy: "single" | "fanout" | "first_success"
  synthesis_profile?: string | null
}

export interface LLMSearchResult {
  answer?: string | null
  context: RequestContext
  evidence: Array<EvidenceItem>
  items: Array<SearchItem>
  meta: SearchMeta
  query: string
  usage: Usage
}

export interface PageInfo {
  limit: number
  next_cursor?: string | null
  total?: number | null
}

export interface ProbeResponse {
  components?: Record<string, "ready" | "not_ready" | "optional_unavailable" | "disabled">
  config_revision?: string | null
  context: RequestContext
  error?: string | null
  ready: boolean
  rollout_mode?: "target"
  source_sha?: string | null
  status: "ok" | "ready" | "not_ready"
  version: string
  worker_source_sha?: string | null
  wrapper_sha?: string | null
}

export interface Provenance {
  attempt?: number | null
  outcome: "success" | "empty" | "failed"
  provider: string
  retrieved_at?: string | null
}

export interface ProviderCatalog {
  context: RequestContext
  items: Array<ProviderCatalogItem>
}

export interface ProviderCatalogItem {
  availability: "available" | "unavailable"
  capabilities: Array<"search" | "llm_search" | "fetch">
  missing_fields?: Array<string>
  provenance: Array<Provenance>
  provider: string
  reason: "available" | "disabled" | "missing_configuration" | "not_eligible"
}

export interface ProviderFailure {
  code: "invalid_request" | "unauthenticated" | "forbidden" | "not_found" | "conflict" | "api_major_mismatch" | "rate_limited" | "payload_too_large" | "unsupported_media_type" | "worker_unavailable" | "worker_not_ready" | "worker_overloaded" | "worker_timeout" | "worker_protocol_mismatch" | "provider_timeout" | "provider_unavailable" | "policy_blocked" | "internal_error"
  provider: string
}

export interface ProviderRef {
  display_name?: string | null
  id: string
  kind: "search" | "llm_search" | "fetch"
}

export interface RequestContext {
  api_major?: 2
  request_id: string
  trace_id?: string | null
}

export interface SearchAttributes {
  authors?: Array<string>
  citation_count?: number | null
  identifiers?: Array<SearchIdentifier>
  language?: string | null
  open_access?: boolean | null
  resource_type?: string | null
  year?: number | null
}

export interface SearchFilters {
  language?: string | null
  open_access?: boolean | null
  resource_type?: string | null
  year_from?: number | null
  year_to?: number | null
}

export interface SearchIdentifier {
  scheme: string
  value: string
}

export interface SearchItem {
  attributes?: SearchAttributes | null
  id: string
  provenance: Array<Provenance>
  rank?: number | null
  snippet?: string | null
  title: string
  url?: string | null
}

export interface SearchMeta {
  failed?: Array<ProviderFailure>
  partial?: boolean
  requested?: Array<string>
  succeeded?: Array<string>
}

export interface SearchPage {
  context: RequestContext
  items: Array<SearchItem>
  meta: SearchMeta
  page: PageInfo
}

export interface SearchPageRequest {
  cursor?: string | null
  limit: number
}

export interface SearchRequest {
  domains: Array<"paper" | "book" | "research_output" | "patent" | "web" | "news" | "images" | "videos" | "social" | "office" | "developer" | "cn_tech" | "knowledge">
  filters?: SearchFilters | null
  page?: SearchPageRequest | null
  providers?: Array<ProviderRef> | null
  query: string
  request_context?: ClientRequestContext | null
}

export interface Usage {
  cost?: number | null
  currency?: string | null
  input_tokens?: number | null
  output_tokens?: number | null
}

export interface ValidationError {
  ctx?: Record<string, unknown>
  input?: unknown
  loc: Array<string | number>
  msg: string
  type: string
}

export interface OperationBinding<Request, Response> {
  method: 'GET' | 'POST'
  path: string
  requestModel: string | null
  responseModel: string
  responseStatuses: readonly number[]
  readonly __request?: Request
  readonly __response?: Response
}

export type OperationBindings = {
  fetch: OperationBinding<FetchRequest, FetchBatch>
  llmSearch: OperationBinding<LLMSearchRequest, LLMSearchResult>
  listProviders: OperationBinding<never, ProviderCatalog>
  search: OperationBinding<SearchRequest, SearchPage>
  healthAlias: OperationBinding<never, ProbeResponse>
  healthz: OperationBinding<never, ProbeResponse>
  readinessAlias: OperationBinding<never, ProbeResponse>
  readyz: OperationBinding<never, ProbeResponse>
}

export const OPERATIONS: OperationBindings = {
  fetch: { method: 'POST', path: '/api/v1/fetch', requestModel: 'FetchRequest', responseModel: 'FetchBatch', responseStatuses: [200] },
  llmSearch: { method: 'POST', path: '/api/v1/llm-search', requestModel: 'LLMSearchRequest', responseModel: 'LLMSearchResult', responseStatuses: [200] },
  listProviders: { method: 'GET', path: '/api/v1/providers', requestModel: null, responseModel: 'ProviderCatalog', responseStatuses: [200] },
  search: { method: 'POST', path: '/api/v1/search', requestModel: 'SearchRequest', responseModel: 'SearchPage', responseStatuses: [200] },
  healthAlias: { method: 'GET', path: '/health', requestModel: null, responseModel: 'ProbeResponse', responseStatuses: [200] },
  healthz: { method: 'GET', path: '/healthz', requestModel: null, responseModel: 'ProbeResponse', responseStatuses: [200] },
  readinessAlias: { method: 'GET', path: '/readiness', requestModel: null, responseModel: 'ProbeResponse', responseStatuses: [200, 503] },
  readyz: { method: 'GET', path: '/readyz', requestModel: null, responseModel: 'ProbeResponse', responseStatuses: [200, 503] },
} as const

export type OperationName = keyof typeof OPERATIONS

export type AuthChannel = 'authorization' | 'x-souwen-token'
export type FetchImplementation = (input: string, init: RequestInit) => Promise<Response>
export interface SouWenClientOptions {
  baseUrl: string
  token?: string
  authChannel?: AuthChannel
  edgeToken?: string
  headers?: Record<string, string>
  fetch?: FetchImplementation
  timeoutMs?: number
  allowedHosts?: readonly string[]
}

export interface RequestOptions {
  requestId?: string
  signal?: AbortSignal
  timeoutMs?: number
  headers?: Record<string, string>
}

export class SouWenSDKError extends Error {
  override name = 'SouWenSDKError'
}
export class ApiMajorMismatchError extends SouWenSDKError {
  override name = 'ApiMajorMismatchError'
  constructor(readonly expected: number, readonly received: string | null) {
    super(`SouWen API major mismatch: expected ${expected}, received ${received ?? 'missing'}`)
  }
}
export class ContractViolationError extends SouWenSDKError {
  override name = 'ContractViolationError'
}
export class SouWenTransportError extends SouWenSDKError {
  override name = 'SouWenTransportError'
}
export class SouWenAPIError extends SouWenSDKError {
  override name = 'SouWenAPIError'
  readonly requestId: string
  constructor(
    readonly statusCode: number,
    readonly payload: ErrorResponse,
    readonly retryAfter: string | null,
    readonly rateLimit: Record<string, string>,
  ) {
    super(`SouWen API error ${statusCode} ${payload.error.code}: ${payload.error.message} (request_id=${payload.context.request_id})`)
    this.requestId = payload.context.request_id
  }
}

const REQUEST_ID = /^[A-Za-z0-9_-]{1,64}$/
const RESERVED_HEADERS = new Set(['accept', 'authorization', 'content-type', 'x-request-id', 'x-souwen-api-major', 'x-souwen-token'])
const RATE_LIMIT_HEADERS = ['X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset'] as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeBaseUrl(baseUrl: string, allowedHosts: readonly string[]): string {
  if (baseUrl === '') return ''
  let url: URL
  try { url = new URL(baseUrl) } catch { throw new TypeError('baseUrl must be a valid HTTP(S) URL') }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new TypeError('baseUrl must be an absolute HTTP(S) URL without userinfo, query, or fragment')
  }
  const loopback = url.hostname === 'localhost' || url.hostname.endsWith('.localhost') || url.hostname === '::1' || /^127(?:\.\d{1,3}){3}$/.test(url.hostname)
  const sameOrigin = typeof window !== 'undefined' && url.origin === window.location.origin
  if (!sameOrigin && !loopback && !allowedHosts.includes(url.host) && !allowedHosts.includes(url.hostname)) {
    throw new TypeError(`baseUrl is not allow-listed: ${url.host}`)
  }
  return url.toString().replace(/\/$/, '')
}

function validateHeaders(headers: Record<string, string> | undefined): Record<string, string> {
  const output = { ...(headers ?? {}) }
  const conflicts = Object.keys(output).filter((key) => RESERVED_HEADERS.has(key.toLowerCase()))
  if (conflicts.length) throw new TypeError(`reserved SDK headers cannot be overridden: ${conflicts.join(', ')}`)
  return output
}

function validateTimeoutMs(timeoutMs: number): number {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be a positive finite number')
  return timeoutMs
}

function awaitCompatibility<Response>(promise: Promise<Response>, signal: AbortSignal | undefined, timeoutMs: number): Promise<Response> {
  validateTimeoutMs(timeoutMs)
  if (signal?.aborted) return Promise.reject(new SouWenTransportError('SouWen HTTP request aborted'))
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (callback: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
      callback()
    }
    const abort = () => finish(() => reject(new SouWenTransportError('SouWen HTTP request aborted')))
    const timer = setTimeout(() => finish(() => reject(new SouWenTransportError('SouWen compatibility probe timed out'))), timeoutMs)
    signal?.addEventListener('abort', abort, { once: true })
    promise.then(
      (value) => finish(() => resolve(value)),
      (error) => finish(() => reject(error)),
    )
  })
}

function makeRequestId(value: string | undefined): string {
  const generated = globalThis.crypto?.randomUUID?.().replace(/-/g, '') ?? `${Date.now()}${Math.random()}`.replace(/[^A-Za-z0-9_-]/g, '')
  const requestId = value ?? generated
  if (!REQUEST_ID.test(requestId)) throw new TypeError('requestId must match [A-Za-z0-9_-]{1,64}')
  return requestId
}

function joinUrl(baseUrl: string, path: string): string { return `${baseUrl}${path}` }

function parseCanonicalJson(response: Response): Promise<unknown> {
  return response.json().catch(() => { throw new ContractViolationError('response body is not canonical JSON') })
}

function verifyHeaders(response: Response): string {
  const major = response.headers.get('X-SouWen-API-Major')
  if (major !== String(SUPPORTED_API_MAJOR)) throw new ApiMajorMismatchError(SUPPORTED_API_MAJOR, major)
  if (response.headers.get('X-SouWen-Rollout-Mode') !== 'target') throw new ContractViolationError('target SDK received invalid X-SouWen-Rollout-Mode')
  const requestId = response.headers.get('X-Request-ID')
  if (!requestId || !REQUEST_ID.test(requestId)) throw new ContractViolationError('response is missing a valid X-Request-ID')
  return requestId
}

function verifyContext(payload: unknown, requestId: string, isProbe = false, isError = false): void {
  if (!isRecord(payload) || !isRecord(payload.context) || payload.context.request_id !== requestId || payload.context.api_major !== SUPPORTED_API_MAJOR) {
    throw new ContractViolationError('response context does not match X-Request-ID or API major')
  }
  if (isProbe && payload.rollout_mode !== 'target') throw new ContractViolationError('probe payload does not identify target rollout')
  if (isError && (!isRecord(payload.error) || payload.error.request_id !== requestId)) throw new ContractViolationError('error request_id does not match X-Request-ID')
}

export class SouWenClient {
  private readonly baseUrl: string
  private readonly baseHeaders: Record<string, string>
  private readonly authHeaders: Record<string, string>
  private readonly requestFetch: FetchImplementation
  private readonly timeoutMs: number
  private compatibilityVerified = false
  private compatibilityPromise: Promise<ProbeResponse> | undefined

  constructor(options: SouWenClientOptions) {
    // This is a Panel/Vite client; this is its only build-time configuration boundary.
    const envHosts = (import.meta.env.VITE_ALLOWED_API_HOSTS ?? '').split(',').map((value: string) => value.trim()).filter(Boolean)
    this.baseUrl = normalizeBaseUrl(options.baseUrl, options.allowedHosts ?? envHosts)
    this.baseHeaders = validateHeaders(options.headers)
    if ((options.token !== undefined && options.token.trim() === '') || (options.edgeToken !== undefined && options.edgeToken.trim() === '')) throw new TypeError('token values cannot be empty')
    const channel = options.authChannel ?? 'authorization'
    if (channel !== 'authorization' && channel !== 'x-souwen-token') throw new TypeError("authChannel must be 'authorization' or 'x-souwen-token'")
    if (options.token && options.edgeToken && channel === 'authorization') throw new TypeError("edgeToken occupies Authorization; use authChannel: 'x-souwen-token' for the application token")
    this.authHeaders = {
      ...(options.edgeToken ? { Authorization: `Bearer ${options.edgeToken}` } : {}),
      ...(options.token ? channel === 'authorization' ? { Authorization: `Bearer ${options.token}` } : { 'X-SouWen-Token': options.token } : {}),
    }
    this.requestFetch = options.fetch ?? globalThis.fetch.bind(globalThis)
    this.timeoutMs = validateTimeoutMs(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  }

  async preflight(options: RequestOptions = {}): Promise<ProbeResponse> {
    if (options.timeoutMs !== undefined) validateTimeoutMs(options.timeoutMs)
    if (options.signal?.aborted) throw new SouWenTransportError('SouWen HTTP request aborted')
    if (this.compatibilityVerified) return this.healthz(options)
    if (!this.compatibilityPromise) {
      // Compatibility is shared across callers, so it always owns its default timeout and request ID.
      this.compatibilityPromise = this.send<ProbeResponse>(OPERATIONS.healthz, undefined, {}).then((response) => {
        this.compatibilityVerified = true
        return response
      }).finally(() => { this.compatibilityPromise = undefined })
    }
    return awaitCompatibility(this.compatibilityPromise, options.signal, options.timeoutMs ?? this.timeoutMs)
  }

  async search(payload: SearchRequest, options: RequestOptions = {}): Promise<SearchPage> { await this.ensureCompatible(options); return this.send(OPERATIONS.search, payload, options) }
  async llmSearch(payload: LLMSearchRequest, options: RequestOptions = {}): Promise<LLMSearchResult> { await this.ensureCompatible(options); return this.send(OPERATIONS.llmSearch, payload, options) }
  async fetch(payload: FetchRequest, options: RequestOptions = {}): Promise<FetchBatch> { await this.ensureCompatible(options); return this.send(OPERATIONS.fetch, payload, options) }
  async listProviders(options: RequestOptions = {}): Promise<ProviderCatalog> { await this.ensureCompatible(options); return this.send(OPERATIONS.listProviders, undefined, options) }
  health(options: RequestOptions = {}): Promise<ProbeResponse> { return this.healthAlias(options) }
  healthAlias(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.healthAlias, undefined, options) }
  async healthz(options: RequestOptions = {}): Promise<ProbeResponse> { const response = await this.send<ProbeResponse>(OPERATIONS.healthz, undefined, options); this.compatibilityVerified = true; return response }
  readiness(options: RequestOptions = {}): Promise<ProbeResponse> { return this.readinessAlias(options) }
  readinessAlias(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.readinessAlias, undefined, options) }
  readyz(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.readyz, undefined, options) }

  private async ensureCompatible(options: RequestOptions): Promise<void> {
    validateTimeoutMs(options.timeoutMs ?? this.timeoutMs)
    if (!this.compatibilityVerified) await this.preflight({ signal: options.signal, timeoutMs: options.timeoutMs ?? this.timeoutMs })
  }

  private async send<Response>(operation: { method: string; path: string; responseStatuses: readonly number[] }, payload: unknown, options: RequestOptions): Promise<Response> {
    const requestId = makeRequestId(options.requestId)
    const requestHeaders = { ...this.baseHeaders, ...this.authHeaders, ...validateHeaders(options.headers), Accept: 'application/json', 'X-SouWen-API-Major': String(SUPPORTED_API_MAJOR), 'X-Request-ID': requestId }
    const timeoutMs = validateTimeoutMs(options.timeoutMs ?? this.timeoutMs)
    const controller = new AbortController()
    let timedOut = false
    const abortUpstream = () => controller.abort(options.signal?.reason)
    if (options.signal?.aborted) abortUpstream()
    options.signal?.addEventListener('abort', abortUpstream, { once: true })
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
    try {
      const response = await this.requestFetch(joinUrl(this.baseUrl, operation.path), { method: operation.method, headers: payload === undefined ? requestHeaders : { ...requestHeaders, 'Content-Type': 'application/json' }, body: payload === undefined ? undefined : JSON.stringify(payload), signal: controller.signal })
      const responseRequestId = verifyHeaders(response)
      const data = await parseCanonicalJson(response)
      if (!operation.responseStatuses.includes(response.status)) {
        verifyContext(data, responseRequestId, false, true)
        const error = data as ErrorResponse
        const rateLimit = Object.fromEntries(RATE_LIMIT_HEADERS.flatMap((name) => { const value = response.headers.get(name); return value === null ? [] : [[name, value]] }))
        throw new SouWenAPIError(response.status, error, response.headers.get('Retry-After'), rateLimit)
      }
      verifyContext(data, responseRequestId, ['/health', '/healthz', '/readiness', '/readyz'].includes(operation.path))
      return data as Response
    } catch (error) {
      if (error instanceof SouWenSDKError) throw error
      if (timedOut) throw new SouWenTransportError('SouWen HTTP request timed out')
      throw new SouWenTransportError('SouWen HTTP request failed')
    } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abortUpstream) }
  }
}
