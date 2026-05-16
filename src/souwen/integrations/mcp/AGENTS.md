# src/souwen/integrations/mcp navigation card

Type: Guardrail card.
This directory implements MCP stdio/server and Streamable HTTP/SSE support.
Read `server.py`, `http_server.py`, tool registrations and MCP integration tests first.
Read this card for MCP lifecycle, HTTP/SSE transport behavior, tool schemas or tool implementation changes.

## Why this is high-risk

- MCP tools expose SouWen capabilities to external agents and clients.
- HTTP/SSE transports can accidentally open network endpoints.
- Tool schema changes affect downstream MCP clients.

## Required before changes

- Confirm whether the change targets stdio, HTTP/SSE or shared tool registration.
- Keep tool implementations calling application APIs, not private route handlers.
- Preserve optional dependency behavior when MCP extras are not installed.

## Do not

- Do not default-open remote MCP HTTP endpoints.
- Do not make base package import require the MCP SDK.
- Do not expose admin/server-only state mutation through public MCP tools without explicit auth design.

## Validation

- `pytest tests/test_integrations/test_mcp_server.py tests/test_integrations/test_mcp_http_server.py -v --tb=short`
