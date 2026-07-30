#!/usr/bin/env python3
"""Generate the dependency-light Panel TypeScript SDK from canonical OpenAPI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = REPOSITORY_ROOT / "contracts/openapi/souwen-openapi-2.0.0rc5.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "panel/src/core/sdk/index.ts"
GENERATOR_VERSION = 2
EXPECTED_VERSION = "2.0.0rc5"
EXPECTED_API_MAJOR = 2
EXPECTED_OPERATIONS = {
    "fetch": ("POST", "/api/v1/fetch", "FetchRequest", "FetchBatch", (200,)),
    "llmSearch": ("POST", "/api/v1/llm-search", "LLMSearchRequest", "LLMSearchResult", (200,)),
    "listProviders": ("GET", "/api/v1/providers", None, "ProviderCatalog", (200,)),
    "search": ("POST", "/api/v1/search", "SearchRequest", "SearchPage", (200,)),
    "healthAlias": ("GET", "/health", None, "ProbeResponse", (200,)),
    "healthz": ("GET", "/healthz", None, "ProbeResponse", (200,)),
    "readinessAlias": ("GET", "/readiness", None, "ProbeResponse", (200, 503)),
    "readyz": ("GET", "/readyz", None, "ProbeResponse", (200, 503)),
}
EXPECTED_SCHEMAS = {
    "ClientRequestContext",
    "ContentMetadata",
    "ErrorDetail",
    "ErrorResponse",
    "EvidenceItem",
    "FetchBatch",
    "FetchContentOptions",
    "FetchMeta",
    "FetchPolicyOptions",
    "FetchRequest",
    "FetchResult",
    "HTTPValidationError",
    "LLMFetchOptions",
    "LLMSearchBudget",
    "LLMSearchRequest",
    "LLMSearchResult",
    "PageInfo",
    "ProbeResponse",
    "Provenance",
    "ProviderCatalog",
    "ProviderCatalogItem",
    "ProviderFailure",
    "ProviderRef",
    "RequestContext",
    "SearchAttributes",
    "SearchFilters",
    "SearchIdentifier",
    "SearchItem",
    "SearchMeta",
    "SearchPage",
    "SearchPageRequest",
    "SearchRequest",
    "Usage",
    "ValidationError",
}
HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
REF_PREFIX = "#/components/schemas/"


class GenerationError(ValueError):
    """The canonical artifact cannot be mapped without widening its contract."""


class _DuplicateKeyError(ValueError):
    pass


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_document(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload, object_pairs_hook=_no_duplicate_pairs)
    except (OSError, json.JSONDecodeError, _DuplicateKeyError) as exc:
        raise GenerationError(f"cannot read canonical OpenAPI artifact {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise GenerationError("canonical OpenAPI root must be an object")
    return document, payload


def _ref_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith(REF_PREFIX):
        raise GenerationError(f"operation schema must use a component ref: {schema!r}")
    return ref.removeprefix(REF_PREFIX)


def _schema_refs(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, child in value.items():
            if key == "$ref":
                if not isinstance(child, str) or not child.startswith(REF_PREFIX):
                    raise GenerationError(f"unsupported schema ref: {child!r}")
                found.add(child.removeprefix(REF_PREFIX))
            else:
                found.update(_schema_refs(child))
        return found
    if isinstance(value, list):
        return set().union(*(_schema_refs(child) for child in value)) if value else set()
    return set()


def _validate_document(document: dict[str, Any]) -> None:
    if document.get("openapi") != "3.1.0":
        raise GenerationError("SDK requires OpenAPI 3.1.0")
    if document.get("info", {}).get("version") != EXPECTED_VERSION:
        raise GenerationError(f"SDK requires OpenAPI version {EXPECTED_VERSION}")
    if document.get("x-souwen-api-major") != EXPECTED_API_MAJOR:
        raise GenerationError(f"SDK requires API major {EXPECTED_API_MAJOR}")
    if document.get("x-souwen-rollout-mode") != "target":
        raise GenerationError("SDK can only be generated from target rollout OpenAPI")
    security = document.get("components", {}).get("securitySchemes", {}).get("UserToken")
    if security != {"type": "http", "scheme": "bearer"}:
        raise GenerationError("UserToken must remain an HTTP bearer security scheme")

    schemas = document.get("components", {}).get("schemas")
    if not isinstance(schemas, dict) or set(schemas) != EXPECTED_SCHEMAS:
        observed = sorted(schemas) if isinstance(schemas, dict) else []
        raise GenerationError(f"unexpected target schema set: {observed}")
    for name, schema in schemas.items():
        if not isinstance(schema, dict):
            raise GenerationError(f"schema {name} must be an object")
        unknown = _schema_refs(schema) - set(schemas)
        if unknown:
            raise GenerationError(f"schema {name} references unknown components: {sorted(unknown)}")

    observed: dict[str, tuple[str, str, str | None, str, tuple[int, ...]]] = {}
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise GenerationError("OpenAPI paths must be an object")
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            raise GenerationError(f"invalid path item: {path}")
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict) or not isinstance(operation.get("operationId"), str):
                raise GenerationError(f"operationId is required for {method.upper()} {path}")
            operation_id = operation["operationId"]
            if operation_id in observed:
                raise GenerationError(f"duplicate operationId: {operation_id}")
            request_schema = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                raise GenerationError(f"operation {operation_id} responses must be an object")
            response_schema = (
                responses.get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            response_model = _ref_name(response_schema)
            if response_model is None or response_model not in schemas:
                raise GenerationError(
                    f"operation {operation_id} must declare a known 200 response model"
                )
            model_statuses: list[int] = []
            for status, response in responses.items():
                try:
                    status_code = int(status)
                except (TypeError, ValueError) as exc:
                    raise GenerationError(
                        f"operation {operation_id} uses non-numeric response status {status!r}"
                    ) from exc
                if not isinstance(response, dict):
                    raise GenerationError(f"response {operation_id} {status} must be an object")
                model = _ref_name(
                    response.get("content", {}).get("application/json", {}).get("schema")
                )
                if model == response_model:
                    model_statuses.append(status_code)
                elif model != "ErrorResponse":
                    raise GenerationError(
                        f"unsupported response model {model!r} for {operation_id} status {status}"
                    )
                headers = response.get("headers", {})
                if not isinstance(headers, dict) or not {
                    "X-SouWen-API-Major",
                    "X-Request-ID",
                    "X-SouWen-Rollout-Mode",
                } <= set(headers):
                    raise GenerationError(f"missing canonical response headers for {operation_id}")
            request_model = _ref_name(request_schema)
            if request_model is not None and request_model not in schemas:
                raise GenerationError(f"operation {operation_id} references unknown request model")
            expected_security = [{"UserToken": []}] if path.startswith("/api/v1/") else []
            if operation.get("security") != expected_security:
                raise GenerationError(f"unexpected security contract for {operation_id}")
            observed[operation_id] = (
                method.upper(),
                path,
                request_model,
                response_model,
                tuple(sorted(model_statuses)),
            )
    if observed != EXPECTED_OPERATIONS:
        raise GenerationError(f"unexpected target operation set: {sorted(observed)}")


def _ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        ref = _ref_name(schema)
        if ref is None:
            raise GenerationError(f"invalid schema ref: {schema!r}")
        return ref
    if "anyOf" in schema:
        variants = schema["anyOf"]
        if (
            not isinstance(variants, list)
            or not variants
            or any(not isinstance(variant, dict) for variant in variants)
        ):
            raise GenerationError(f"invalid anyOf: {schema!r}")
        return " | ".join(dict.fromkeys(_ts_type(variant) for variant in variants))
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            raise GenerationError(f"invalid enum: {schema!r}")
        return " | ".join(json.dumps(value) for value in values)
    if "const" in schema:
        return json.dumps(schema["const"])
    schema_type = schema.get("type")
    if schema_type == "null":
        return "null"
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise GenerationError(f"array items are required: {schema!r}")
        return f"Array<{_ts_type(items)}>"
    if schema_type == "object":
        if "properties" in schema:
            raise GenerationError("inline object models with properties are not supported")
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional)}>"
        if additional is False:
            raise GenerationError("inline closed object models are not supported")
        return "Record<string, unknown>"
    if schema_type is None and set(schema) <= {"title"}:
        return "unknown"
    raise GenerationError(f"unsupported schema shape: {schema!r}")


def _render_dtos(document: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    schemas = document["components"]["schemas"]
    for name, schema in schemas.items():
        if schema.get("type") != "object":
            lines.extend([f"export type {name} = {_ts_type(schema)}", ""])
            continue
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise GenerationError(f"schema {name}.properties must be an object")
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise GenerationError(f"schema {name}.required must be a string list")
        lines.append(f"export interface {name} {{")
        for field, field_schema in properties.items():
            if not isinstance(field, str) or not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", field):
                raise GenerationError(f"unsupported TypeScript field name: {name}.{field}")
            if not isinstance(field_schema, dict):
                raise GenerationError(f"field schema must be an object: {name}.{field}")
            optional = "" if field in required else "?"
            lines.append(f"  {field}{optional}: {_ts_type(field_schema)}")
        lines.extend(["}", ""])
    return lines


def _search_domains(document: dict[str, Any]) -> list[str]:
    try:
        values = document["components"]["schemas"]["SearchRequest"]["properties"]["domains"][
            "items"
        ]["enum"]
    except (KeyError, TypeError) as exc:
        raise GenerationError("SearchRequest.domains must expose one enum") from exc
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value for value in values)
        or len(values) != len(set(values))
    ):
        raise GenerationError("SearchRequest.domains enum must contain unique strings")
    return values


def _render(document: dict[str, Any], artifact_payload: bytes) -> str:
    artifact_sha = hashlib.sha256(artifact_payload).hexdigest()
    operation_lines = []
    for name, (method, path, request, response, statuses) in EXPECTED_OPERATIONS.items():
        request_model = repr(request) if request else "null"
        operation_lines.append(
            f"  {name}: {{ method: {method!r}, path: {path!r}, requestModel: "
            f"{request_model}, responseModel: {response!r}, "
            f"responseStatuses: {list(statuses)!r} }},"
        )
    dto_lines = _render_dtos(document)
    return "\n".join(
        [
            "/* Generated from contracts/openapi/souwen-openapi-2.0.0rc5.json; do not edit. */",
            f"/* generator_version={GENERATOR_VERSION} */",
            f"/* openapi_sha256={artifact_sha} */",
            "",
            f"export const SDK_VERSION = {document['info']['version']!r} as const",
            f"export const SUPPORTED_API_MAJOR = {document['x-souwen-api-major']} as const",
            f"export const OPENAPI_SHA256 = {artifact_sha!r} as const",
            "export const DEFAULT_TIMEOUT_MS = 125_000",
            f"export const SEARCH_DOMAINS = {json.dumps(_search_domains(document))} as const",
            "export type SearchDomain = typeof SEARCH_DOMAINS[number]",
            "",
            *dto_lines,
            "export interface OperationBinding<Request, Response> {",
            "  method: 'GET' | 'POST'",
            "  path: string",
            "  requestModel: string | null",
            "  responseModel: string",
            "  responseStatuses: readonly number[]",
            "  readonly __request?: Request",
            "  readonly __response?: Response",
            "}",
            "",
            "export type OperationBindings = {",
            "  fetch: OperationBinding<FetchRequest, FetchBatch>",
            "  llmSearch: OperationBinding<LLMSearchRequest, LLMSearchResult>",
            "  listProviders: OperationBinding<never, ProviderCatalog>",
            "  search: OperationBinding<SearchRequest, SearchPage>",
            "  healthAlias: OperationBinding<never, ProbeResponse>",
            "  healthz: OperationBinding<never, ProbeResponse>",
            "  readinessAlias: OperationBinding<never, ProbeResponse>",
            "  readyz: OperationBinding<never, ProbeResponse>",
            "}",
            "",
            "export const OPERATIONS: OperationBindings = {",
            *operation_lines,
            "} as const",
            "",
            "export type OperationName = keyof typeof OPERATIONS",
            "",
            "export type AuthChannel = 'authorization' | 'x-souwen-token'",
            "export type FetchImplementation = (input: string, init: RequestInit) => Promise<Response>",
            "export interface SouWenClientOptions {",
            "  baseUrl: string",
            "  token?: string",
            "  authChannel?: AuthChannel",
            "  edgeToken?: string",
            "  headers?: Record<string, string>",
            "  fetch?: FetchImplementation",
            "  timeoutMs?: number",
            "  allowedHosts?: readonly string[]",
            "}",
            "",
            "export interface RequestOptions {",
            "  requestId?: string",
            "  signal?: AbortSignal",
            "  timeoutMs?: number",
            "  headers?: Record<string, string>",
            "}",
            "",
            "export class SouWenSDKError extends Error {",
            "  override name = 'SouWenSDKError'",
            "}",
            "export class ApiMajorMismatchError extends SouWenSDKError {",
            "  override name = 'ApiMajorMismatchError'",
            "  constructor(readonly expected: number, readonly received: string | null) {",
            "    super(`SouWen API major mismatch: expected ${expected}, received ${received ?? 'missing'}`)",
            "  }",
            "}",
            "export class ContractViolationError extends SouWenSDKError {",
            "  override name = 'ContractViolationError'",
            "}",
            "export class SouWenTransportError extends SouWenSDKError {",
            "  override name = 'SouWenTransportError'",
            "}",
            "export class SouWenAPIError extends SouWenSDKError {",
            "  override name = 'SouWenAPIError'",
            "  readonly requestId: string",
            "  constructor(",
            "    readonly statusCode: number,",
            "    readonly payload: ErrorResponse,",
            "    readonly retryAfter: string | null,",
            "    readonly rateLimit: Record<string, string>,",
            "  ) {",
            "    super(`SouWen API error ${statusCode} ${payload.error.code}: ${payload.error.message} (request_id=${payload.context.request_id})`)",
            "    this.requestId = payload.context.request_id",
            "  }",
            "}",
            "",
            "const REQUEST_ID = /^[A-Za-z0-9_-]{1,64}$/",
            "const RESERVED_HEADERS = new Set(['accept', 'authorization', 'content-type', 'x-request-id', 'x-souwen-api-major', 'x-souwen-token'])",
            "const RATE_LIMIT_HEADERS = ['X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset'] as const",
            "",
            "function isRecord(value: unknown): value is Record<string, unknown> {",
            "  return typeof value === 'object' && value !== null && !Array.isArray(value)",
            "}",
            "",
            "function normalizeBaseUrl(baseUrl: string, allowedHosts: readonly string[]): string {",
            "  if (baseUrl === '') return ''",
            "  let url: URL",
            "  try { url = new URL(baseUrl) } catch { throw new TypeError('baseUrl must be a valid HTTP(S) URL') }",
            "  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {",
            "    throw new TypeError('baseUrl must be an absolute HTTP(S) URL without userinfo, query, or fragment')",
            "  }",
            "  const loopback = url.hostname === 'localhost' || url.hostname.endsWith('.localhost') || url.hostname === '::1' || /^127(?:\\.\\d{1,3}){3}$/.test(url.hostname)",
            "  const sameOrigin = typeof window !== 'undefined' && url.origin === window.location.origin",
            "  if (!sameOrigin && !loopback && !allowedHosts.includes(url.host) && !allowedHosts.includes(url.hostname)) {",
            "    throw new TypeError(`baseUrl is not allow-listed: ${url.host}`)",
            "  }",
            "  return url.toString().replace(/\\/$/, '')",
            "}",
            "",
            "function validateHeaders(headers: Record<string, string> | undefined): Record<string, string> {",
            "  const output = { ...(headers ?? {}) }",
            "  const conflicts = Object.keys(output).filter((key) => RESERVED_HEADERS.has(key.toLowerCase()))",
            "  if (conflicts.length) throw new TypeError(`reserved SDK headers cannot be overridden: ${conflicts.join(', ')}`)",
            "  return output",
            "}",
            "",
            "function validateTimeoutMs(timeoutMs: number): number {",
            "  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be a positive finite number')",
            "  return timeoutMs",
            "}",
            "",
            "function awaitCompatibility<Response>(promise: Promise<Response>, signal: AbortSignal | undefined, timeoutMs: number): Promise<Response> {",
            "  validateTimeoutMs(timeoutMs)",
            "  if (signal?.aborted) return Promise.reject(new SouWenTransportError('SouWen HTTP request aborted'))",
            "  return new Promise((resolve, reject) => {",
            "    let settled = false",
            "    const finish = (callback: () => void) => {",
            "      if (settled) return",
            "      settled = true",
            "      clearTimeout(timer)",
            "      signal?.removeEventListener('abort', abort)",
            "      callback()",
            "    }",
            "    const abort = () => finish(() => reject(new SouWenTransportError('SouWen HTTP request aborted')))",
            "    const timer = setTimeout(() => finish(() => reject(new SouWenTransportError('SouWen compatibility probe timed out'))), timeoutMs)",
            "    signal?.addEventListener('abort', abort, { once: true })",
            "    promise.then(",
            "      (value) => finish(() => resolve(value)),",
            "      (error) => finish(() => reject(error)),",
            "    )",
            "  })",
            "}",
            "",
            "function makeRequestId(value: string | undefined): string {",
            "  const generated = globalThis.crypto?.randomUUID?.().replace(/-/g, '') ?? `${Date.now()}${Math.random()}`.replace(/[^A-Za-z0-9_-]/g, '')",
            "  const requestId = value ?? generated",
            "  if (!REQUEST_ID.test(requestId)) throw new TypeError('requestId must match [A-Za-z0-9_-]{1,64}')",
            "  return requestId",
            "}",
            "",
            "function joinUrl(baseUrl: string, path: string): string { return `${baseUrl}${path}` }",
            "",
            "function parseCanonicalJson(response: Response): Promise<unknown> {",
            "  return response.json().catch(() => { throw new ContractViolationError('response body is not canonical JSON') })",
            "}",
            "",
            "function verifyHeaders(response: Response): string {",
            "  const major = response.headers.get('X-SouWen-API-Major')",
            "  if (major !== String(SUPPORTED_API_MAJOR)) throw new ApiMajorMismatchError(SUPPORTED_API_MAJOR, major)",
            "  if (response.headers.get('X-SouWen-Rollout-Mode') !== 'target') throw new ContractViolationError('target SDK received invalid X-SouWen-Rollout-Mode')",
            "  const requestId = response.headers.get('X-Request-ID')",
            "  if (!requestId || !REQUEST_ID.test(requestId)) throw new ContractViolationError('response is missing a valid X-Request-ID')",
            "  return requestId",
            "}",
            "",
            "function verifyContext(payload: unknown, requestId: string, isProbe = false, isError = false): void {",
            "  if (!isRecord(payload) || !isRecord(payload.context) || payload.context.request_id !== requestId || payload.context.api_major !== SUPPORTED_API_MAJOR) {",
            "    throw new ContractViolationError('response context does not match X-Request-ID or API major')",
            "  }",
            "  if (isProbe && payload.rollout_mode !== 'target') throw new ContractViolationError('probe payload does not identify target rollout')",
            "  if (isError && (!isRecord(payload.error) || payload.error.request_id !== requestId)) throw new ContractViolationError('error request_id does not match X-Request-ID')",
            "}",
            "",
            "export class SouWenClient {",
            "  private readonly baseUrl: string",
            "  private readonly baseHeaders: Record<string, string>",
            "  private readonly authHeaders: Record<string, string>",
            "  private readonly requestFetch: FetchImplementation",
            "  private readonly timeoutMs: number",
            "  private compatibilityVerified = false",
            "  private compatibilityPromise: Promise<ProbeResponse> | undefined",
            "",
            "  constructor(options: SouWenClientOptions) {",
            "    // This is a Panel/Vite client; this is its only build-time configuration boundary.",
            "    const envHosts = (import.meta.env.VITE_ALLOWED_API_HOSTS ?? '').split(',').map((value: string) => value.trim()).filter(Boolean)",
            "    this.baseUrl = normalizeBaseUrl(options.baseUrl, options.allowedHosts ?? envHosts)",
            "    this.baseHeaders = validateHeaders(options.headers)",
            "    if ((options.token !== undefined && options.token.trim() === '') || (options.edgeToken !== undefined && options.edgeToken.trim() === '')) throw new TypeError('token values cannot be empty')",
            "    const channel = options.authChannel ?? 'authorization'",
            "    if (channel !== 'authorization' && channel !== 'x-souwen-token') throw new TypeError(\"authChannel must be 'authorization' or 'x-souwen-token'\")",
            "    if (options.token && options.edgeToken && channel === 'authorization') throw new TypeError(\"edgeToken occupies Authorization; use authChannel: 'x-souwen-token' for the application token\")",
            "    this.authHeaders = {",
            "      ...(options.edgeToken ? { Authorization: `Bearer ${options.edgeToken}` } : {}),",
            "      ...(options.token ? channel === 'authorization' ? { Authorization: `Bearer ${options.token}` } : { 'X-SouWen-Token': options.token } : {}),",
            "    }",
            "    this.requestFetch = options.fetch ?? globalThis.fetch.bind(globalThis)",
            "    this.timeoutMs = validateTimeoutMs(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)",
            "  }",
            "",
            "  async preflight(options: RequestOptions = {}): Promise<ProbeResponse> {",
            "    if (options.timeoutMs !== undefined) validateTimeoutMs(options.timeoutMs)",
            "    if (options.signal?.aborted) throw new SouWenTransportError('SouWen HTTP request aborted')",
            "    if (this.compatibilityVerified) return this.healthz(options)",
            "    if (!this.compatibilityPromise) {",
            "      // Compatibility is shared across callers, so it always owns its default timeout and request ID.",
            "      this.compatibilityPromise = this.send<ProbeResponse>(OPERATIONS.healthz, undefined, {}).then((response) => {",
            "        this.compatibilityVerified = true",
            "        return response",
            "      }).finally(() => { this.compatibilityPromise = undefined })",
            "    }",
            "    return awaitCompatibility(this.compatibilityPromise, options.signal, options.timeoutMs ?? this.timeoutMs)",
            "  }",
            "",
            "  async search(payload: SearchRequest, options: RequestOptions = {}): Promise<SearchPage> { await this.ensureCompatible(options); return this.send(OPERATIONS.search, payload, options) }",
            "  async llmSearch(payload: LLMSearchRequest, options: RequestOptions = {}): Promise<LLMSearchResult> { await this.ensureCompatible(options); return this.send(OPERATIONS.llmSearch, payload, options) }",
            "  async fetch(payload: FetchRequest, options: RequestOptions = {}): Promise<FetchBatch> { await this.ensureCompatible(options); return this.send(OPERATIONS.fetch, payload, options) }",
            "  async listProviders(options: RequestOptions = {}): Promise<ProviderCatalog> { await this.ensureCompatible(options); return this.send(OPERATIONS.listProviders, undefined, options) }",
            "  health(options: RequestOptions = {}): Promise<ProbeResponse> { return this.healthAlias(options) }",
            "  healthAlias(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.healthAlias, undefined, options) }",
            "  async healthz(options: RequestOptions = {}): Promise<ProbeResponse> { const response = await this.send<ProbeResponse>(OPERATIONS.healthz, undefined, options); this.compatibilityVerified = true; return response }",
            "  readiness(options: RequestOptions = {}): Promise<ProbeResponse> { return this.readinessAlias(options) }",
            "  readinessAlias(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.readinessAlias, undefined, options) }",
            "  readyz(options: RequestOptions = {}): Promise<ProbeResponse> { return this.send(OPERATIONS.readyz, undefined, options) }",
            "",
            "  private async ensureCompatible(options: RequestOptions): Promise<void> {",
            "    validateTimeoutMs(options.timeoutMs ?? this.timeoutMs)",
            "    if (!this.compatibilityVerified) await this.preflight({ signal: options.signal, timeoutMs: options.timeoutMs ?? this.timeoutMs })",
            "  }",
            "",
            "  private async send<Response>(operation: { method: string; path: string; responseStatuses: readonly number[] }, payload: unknown, options: RequestOptions): Promise<Response> {",
            "    const requestId = makeRequestId(options.requestId)",
            "    const requestHeaders = { ...this.baseHeaders, ...this.authHeaders, ...validateHeaders(options.headers), Accept: 'application/json', 'X-SouWen-API-Major': String(SUPPORTED_API_MAJOR), 'X-Request-ID': requestId }",
            "    const timeoutMs = validateTimeoutMs(options.timeoutMs ?? this.timeoutMs)",
            "    const controller = new AbortController()",
            "    let timedOut = false",
            "    const abortUpstream = () => controller.abort(options.signal?.reason)",
            "    if (options.signal?.aborted) abortUpstream()",
            "    options.signal?.addEventListener('abort', abortUpstream, { once: true })",
            "    const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)",
            "    try {",
            "      const response = await this.requestFetch(joinUrl(this.baseUrl, operation.path), { method: operation.method, headers: payload === undefined ? requestHeaders : { ...requestHeaders, 'Content-Type': 'application/json' }, body: payload === undefined ? undefined : JSON.stringify(payload), signal: controller.signal })",
            "      const responseRequestId = verifyHeaders(response)",
            "      const data = await parseCanonicalJson(response)",
            "      if (!operation.responseStatuses.includes(response.status)) {",
            "        verifyContext(data, responseRequestId, false, true)",
            "        const error = data as ErrorResponse",
            "        const rateLimit = Object.fromEntries(RATE_LIMIT_HEADERS.flatMap((name) => { const value = response.headers.get(name); return value === null ? [] : [[name, value]] }))",
            "        throw new SouWenAPIError(response.status, error, response.headers.get('Retry-After'), rateLimit)",
            "      }",
            "      verifyContext(data, responseRequestId, ['/health', '/healthz', '/readiness', '/readyz'].includes(operation.path))",
            "      return data as Response",
            "    } catch (error) {",
            "      if (error instanceof SouWenSDKError) throw error",
            "      if (timedOut) throw new SouWenTransportError('SouWen HTTP request timed out')",
            "      throw new SouWenTransportError('SouWen HTTP request failed')",
            "    } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abortUpstream) }",
            "  }",
            "}",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="write the generated TypeScript SDK")
    action.add_argument("--check", action="store_true", help="verify the generated TypeScript SDK")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document, artifact_payload = _load_document(args.artifact)
        _validate_document(document)
        rendered = _render(document, artifact_payload).encode("utf-8")
    except GenerationError as exc:
        print(f"TypeScript SDK generation failed: {exc}", file=sys.stderr)
        return 2
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered)
        print(f"wrote generated TypeScript SDK to {args.output}")
        return 0
    if not args.output.is_file() or args.output.read_bytes() != rendered:
        print(f"generated TypeScript SDK is stale: {args.output}", file=sys.stderr)
        return 1
    print(f"generated TypeScript SDK is reproducible: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
