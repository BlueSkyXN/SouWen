# src/souwen/integrations navigation card

Type: Domain card.
This directory contains external protocol integrations, mainly MCP.
Read `mcp_server.py`, `integrations/mcp/`, `docs/plugin-integration-spec.md`, and matching `tests/test_integrations/` files first.
Read this card when changing integration entry points, optional dependency behavior, tool wiring or protocol adapters.

## Local invariants

- Integrations should call existing application APIs and registry views.
- Optional dependency absence must produce clear ImportError/skip behavior.
- Integration-specific types should not leak into core public models.
- Network servers or transports must only start from explicit commands/configured lifecycles.

## Do not

- Do not start network servers at import time.
- Do not duplicate search/fetch business logic here.
- Do not make the core package require MCP SDK at import time.

## Validation

- `pytest tests/test_integrations -v --tb=short`
