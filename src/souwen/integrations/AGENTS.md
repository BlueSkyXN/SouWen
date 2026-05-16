# src/souwen/integrations navigation card

This directory contains external protocol integrations, mainly MCP.
Read `mcp_server.py`, `integrations/mcp/`, `docs/plugin-integration-spec.md`, and `tests/test_integrations/` first.
Read this card when changing integration entry points or tool wiring.

## Local invariants

- Integrations should call existing application APIs and registry views.
- Optional dependency absence must produce clear ImportError/skip behavior.
- Integration-specific types should not leak into core public models.

## Do not

- Do not start network servers at import time.
- Do not duplicate search/fetch business logic here.

## Validation

- `pytest tests/test_integrations -v --tb=short`
