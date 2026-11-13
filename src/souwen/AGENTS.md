# src/souwen navigation card

Type: Domain card. This is the main Python package.
Read this card when changing package-level APIs, imports, shared models or cross-layer behavior.

## Layout (3.x)

- `agent.py` — the facade every entry point shares; `__init__.py` re-exports `search`/`fetch`.
- `modules/search|fetch` — orchestration; `modules/search/data/census_order.py` holds the
  census-derived candidate order.
- `common_runtime/` — transport, egress ladder, SSRF, resilience.
- `providers/` — one package per source; `manifest.py` is the identity source of truth.
- `platform/` — SPI/spec/registry/manager.
- `server/` — FastAPI app, MCP server, doctor, runtime wiring.

## Local invariants

- Package imports stay light; optional provider dependencies load lazily.
- `browser_pinning_proxy.py` keeps connection-level SSRF pinning for browser egress.
- `fetch_target.py` SSRF logic must not change; its tests move with it unchanged.

## Do not

- Do not bypass `ProviderManager` or create a second selection registry.
- Do not reintroduce `/api/v1/*`, frozen OpenAPI, generated SDKs, Panel, Admin, or LLM Search.
