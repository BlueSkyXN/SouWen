# Phase 1：Current Security Behavior Baseline

**状态**：current-only baseline；本文件不定义 target security contract。

**Fixture**：[current_security_behavior_v1.json](../../../tests/contracts/fixtures/current_security_behavior_v1.json)

**Deterministic check**：[test_current_security_behavior_contract.py](../../../tests/contracts/test_current_security_behavior_contract.py)

## Scope

本基线冻结仓库当前已实现并有确定性证据的 SSRF、safe redirect、proxy/browser request
guard、request correlation、error/config redaction 与 application credential precedence。它不
断言网络可达性、browser runtime、provider security、性能阈值或未来 DTO/error API。

Fixture 是 language-neutral JSON，不携带真实 token、cookie、password、private hostname 或
user HOME 路径。测试只用 fake DNS、fake transport、monkeypatch 和 TestClient；不会发出网络
请求、启动 browser 或读取本机配置。

## Current evidence mapping

| Area | Current behavior frozen here | Evidence |
|---|---|---|
| URL scheme and direct host SSRF | `resolve_fetch_target()` only permits `http`/`https`, rejects URL userinfo, localhost, private/loopback/link-local/reserved/multicast literals, legacy IPv4 numeric syntax and IPv4 embedded in relevant IPv6 forms. | `src/souwen/web/fetch.py`; `tests/test_web/test_fetch.py`; `tests/test_web/test_ssrf_binding.py` |
| DNS SSRF | Hostname resolution examines all returned addresses and fails closed when any is blocked; accepted targets are bound to a validated IP `connect_url` with original Host/SNI metadata. | `src/souwen/web/fetch.py`; `tests/test_web/test_ssrf_binding.py` |
| Redirect revalidation | `BaseScraper._fetch_with_safe_redirects()` resolves and checks every hop. A public first hop redirecting to a private literal is blocked before a second transport request. | `src/souwen/core/scraper/base.py`; `tests/test_web/test_ssrf_binding.py` |
| Proxy no-bypass | Bound HTTP requests use `target.connect_url`, `Host`/SNI from original authority, `follow_redirects=False`, `trust_env=False`; explicit SouWen proxy remains attached. Ambient proxy environment is not trusted. | `src/souwen/core/scraper/base.py`; `tests/test_web/test_ssrf_binding.py` |
| Browser no-bypass | Scrapling dynamic/stealth browser modes install `page.route("**/*", ...)` and call the same `validate_fetch_url()` for navigation/subresource/XHR/fetch requests; blocked URLs are aborted. | `src/souwen/web/scrapling_fetcher.py`; `tests/test_web/test_scrapling_fetcher.py` |
| Request ID and errors | Middleware accepts safe request IDs or generates one, writes `X-Request-ID` and `X-Response-Time`; global HTTP/validation errors use current flat `{error, detail, request_id}` and redact error detail. | `src/souwen/server/middleware.py`; `src/souwen/server/app.py`; `tests/test_server/test_app.py` |
| Auth header precedence | `X-SouWen-Token` is the application credential channel when present and takes precedence over `Authorization`; an explicitly invalid custom token does not fall back to `Authorization`. | `src/souwen/server/auth.py`; `tests/test_server/test_app.py` |
| Secret/config redaction | Secret-shaped fields and URL userinfo/query credentials are replaced with `***`; LLM-search gateway config additionally hides non-empty `base_url`. | `src/souwen/core/redaction.py`; `src/souwen/server/routes/admin/config.py`; `tests/test_redaction.py`; `tests/test_server/test_app.py` |

## Current limitations intentionally not promoted

1. Current `skip_ssrf_check` exists on the internal `fetch_content()` function for controlled test/internal
   paths. It is not an External API authorization mechanism and is not exposed as a current REST request field.
2. Current error validation uses HTTP 422 through FastAPI/Pydantic handlers. This is a present behavior fact,
   not a decision on the target validation status convention.
3. Current auth is route/config dependent: Search uses `check_search_auth`, Fetch uses `require_auth`, and
   `SOUWEN_ADMIN_OPEN=1` is an explicit current Admin-only escape hatch. It does not determine the future
   External Data API default.
4. A browser/proxy guard is a safety control, not proof that all third-party providers, browser runtime
   variants or deployed proxies have been externally tested.

## Open decision dependencies

| Open item | Deliberately not decided here |
|---|---|
| Q-006 | Target Fetch content type, length and quality thresholds. |
| Q-007 | Target External Data API authentication/default guest policy. |
| API-Q-001 | Target invalid-input HTTP status convention. |
| Q-008 | Target performance, distributed limiting and operational security measurement. |
| REL-Q-001 | Probe-path cutover from current `/health`/`/readiness`. |
