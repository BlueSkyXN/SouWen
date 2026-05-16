# src/souwen/integrations/mcp navigation card

This directory implements MCP stdio/server and Streamable HTTP/SSE support.
Read `server.py`, `http_server.py`, `tools/`, and MCP integration tests first.
Read this card for MCP lifecycle, transport behavior or tool changes.

## Local invariants

- Network MCP should only be enabled by config.
- HTTP/SSE lifespan must start and stop safely under FastAPI lifecycle.
- Tools should call application APIs, not private route handlers.

## Do not

- Do not default-open remote MCP HTTP endpoints.
- Do not make the core package require MCP SDK at import time.

## Validation

- `pytest tests/test_integrations/test_mcp_server.py tests/test_integrations/test_mcp_http_server.py -v --tb=short`
