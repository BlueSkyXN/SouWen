# Phase 1B：Current API Behavior Mapping and Golden Fixtures

**状态**：current-only baseline；冻结现有仓库行为，不定义目标 API。

**Fixture**：[`tests/contracts/fixtures/current_api_golden.json`](../../../tests/contracts/fixtures/current_api_golden.json)

**验证**：[`tests/contracts/test_current_api_contract.py`](../../../tests/contracts/test_current_api_contract.py)

**仓库锚点**：repository root；所有证据路径均相对仓库根目录。

## 1. 目的与边界

这组 fixture 是 language-neutral JSON：它只表达 HTTP method/path、JSON request/response 示例、
OpenAPI schema reference 和当前错误/认证观察值。Python test 只负责解析该 JSON，并将其与当前
FastAPI OpenAPI、Pydantic schema 与无需外部网络的 route 行为比对。它不是 generated client，
不是 future OpenAPI artifact，也不把任何 current DTO 提升为 `2.0.0` canonical DTO。

尤其是，下列名字仅是目标 HLD/SPEC-01 中的迁移方向，**不是当前 route**：
`POST /api/v1/search`、`POST /api/v1/llm-search`、`GET /api/v1/providers`、`/healthz`、`/readyz`。

## 2. Current behavior mapping

| Fixture key | Current route / behavior | Current evidence | Fixture scope |
|---|---|---|---|
| `health` | `GET /health` → `HealthResponse`，无 auth，包含 `status`、`version`、`source_sha`。 | `src/souwen/server/app.py`；`src/souwen/server/schemas/common.py`；`tests/test_server/test_app.py` | 200 JSON example、OpenAPI ref、runtime route. |
| `readiness` | `GET /readiness` → `ReadinessResponse`，只做 local config/registry checks，不做网络调用；ready false 时是 503。 | `src/souwen/server/app.py`；`src/souwen/server/schemas/common.py`；`tests/test_server/test_app.py` | ready 200 JSON example、OpenAPI ref、runtime route. |
| `search_paper` | `GET /api/v1/search/paper`，query params `q`、`sources`、`per_page`、`timeout`；成功返回 `SearchPaperResponse`。 | `src/souwen/server/routes/search.py`；`src/souwen/server/schemas/search.py`；`tests/test_server/test_openapi_contract.py` | request query example、empty success response shape、OpenAPI ref/parameters. |
| `enriched_web_search` | `POST /api/v1/search/web/enriched`，是 current explicit model-bound enriched search；并非目标 `/llm-search`。 | `src/souwen/server/routes/search.py`；`src/souwen/server/schemas/search.py`；`tests/test_server/test_enriched_search_route.py` | request/response schema sample，nullable usage 的 unknown 语义。 |
| `fetch` | `POST /api/v1/fetch`，current Admin auth，`urls` 1–20、legacy `provider`、`providers`、`fallback`/`fanout`；成功返回 current `souwen.models.FetchResponse`。 | `src/souwen/server/routes/fetch.py`；`src/souwen/server/schemas/fetch.py`；`src/souwen/models.py`；`tests/test_server/test_fetch_route.py` | request/response sample、deprecated `provider` summary field、OpenAPI ref. |
| `errors` | Global current error body is flat `{error, detail, request_id}`; 404/422/401 route behavior is tested. | `src/souwen/server/app.py`；`src/souwen/server/schemas/common.py`；`tests/test_server/test_app.py` | current error examples and safe runtime assertions. |
| `auth` | Current app credential accepts `Authorization: Bearer` or priority `X-SouWen-Token`; Search depends on `user_password` / `guest_enabled`; Fetch uses current Admin dependency. | `src/souwen/server/auth.py`；`src/souwen/server/routes/search.py`；`src/souwen/server/routes/fetch.py` | auth header metadata and deterministic unauthorized cases. |

## 3. Intentional current limitations preserved by the fixture

1. Current OpenAPI declares typed `200` request/response schemas for the operations above, but current error
   responses are supplied by global exception handlers and are not registered as an `ErrorResponse` component
   in the generated OpenAPI document. The fixture therefore validates current errors through runtime responses
   and `ErrorResponse` Pydantic parsing, not through a non-existent OpenAPI component.
2. Current Search response shapes are endpoint-specific: paper/book/patent use `sources`, web uses `engines`,
   and several `results` fields are `list[dict]`. The fixture freezes `search_paper` only; it does not claim a
   unified current Search DTO.
3. The current Fetch `provider` field is explicitly deprecated by `souwen.models.FetchResponse`; the fixture
   records it as current behavior and does not endorse it for a future canonical DTO.
4. `source_sha`, runtime `version`, configured provider availability and exact error `detail` text can vary by
   configuration or release. Fixture examples use deterministic placeholders and tests validate the stable
   shape/code/header rule instead of treating those values as a release identity assertion.

## 4. Fixture authoring rules

- Keep fixtures JSON-only, UTF-8, no token/cookie/real URL credential/private service data.
- Add a current fixture only after verifying the route, schema/OpenAPI and deterministic route test. Do not
  add a target path merely because it appears in HLD or SPEC-01.
- A behavior change to an existing current fixture must update its mapping row, fixture and deterministic test
  in the same change. Generated OpenAPI documents are not hand-edited here.
- Do not add source/provider live results: the fixture models static contract shape and uses no network.

## 5. Decision dependencies that remain open

This baseline makes no decision and must not be used to close the following items:

| Open item | Not decided by this fixture |
|---|---|
| Q-004 | Multi-source default strategy, ordering, deduplication and partial-success policy. |
| Q-005 | LLM evidence/usage minimum and citation completeness. |
| Q-006 | Fetch content type, length and quality thresholds. |
| Q-007 | External Data API default authentication policy. |
| Q-008 | Performance, concurrency, memory, image/cold-start targets and final quota model. |
| API-Q-001 | Future API input-validation status convention (400 vs 422). |
| REL-Q-001 | Current `/health`/`/readiness` versus target probe-path cutover policy. |
