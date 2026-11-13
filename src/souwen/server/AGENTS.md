# src/souwen/server navigation card

Type: Domain card. Read when changing the API app, auth, limiter, MCP server, doctor, or runtime wiring.

## Layout (3.x)

- `app.py` — FastAPI app: `POST /search`, `POST /fetch`, `GET /sources`, `GET /healthz`,
  and `/mcp` (FastMCP streamable HTTP mounted at the root, protected by `McpAuthMiddleware`).
- `agent_api.py` — the flat agent routes; `mcp_server.py` — the two-tool MCP server.
- `auth.py` — fail-closed user-credential check (Bearer / `X-SouWen-Token`); semantics
  must not loosen.
- `browser_executor.py` — fetch-ladder browser executor (in-process pool).
- `doctor.py` — `souwen doctor --live` per-egress census.
- `v2_runtime.py` — provider wiring/composition root (dissolution is planned in P4).
- `warp.py` — WARP lifecycle (wireproxy / usque / external only).

## Do not

- Do not remove auth or rate limiting from the agent routes or `/mcp`.
- Do not add routes beyond the SPEC 2.4 surface.
