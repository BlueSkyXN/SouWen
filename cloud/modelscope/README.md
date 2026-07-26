# SouWen target-only v2 API

ModelScope image exposes only target v2 Search, LLM Search and Fetch:

| Method | Path |
|---|---|
| POST | `/api/v1/search` |
| POST | `/api/v1/llm-search` |
| POST | `/api/v1/fetch` |
| GET | `/api/v1/providers` |
| GET | `/healthz`、`/readyz` |

`/health` 与 `/readiness` 是 retained 2.x aliases. `/api/v1/providers` is the safe
ProviderManifest/ManifestRegistry/ProviderManager catalog projection; `/sources` is retired.
Admin only retains authenticated read-only `/api/v1/admin/config`, `/doctor`, and `/ping`.

Set `SOUWEN_USER_PASSWORD` to protect Data API and `SOUWEN_ADMIN_PASSWORD` to protect Admin.
There is no rollout switch and no public citation, detail, archive-save, recursive-crawl,
browser-fetch product entry, or legacy enriched-search endpoint.

ModelScope listens on port `7860`; its Docker healthcheck uses `/healthz`. Build with an immutable
`SOUWEN_REF=<40-character SHA>`; the all-zero template value fails closed.
