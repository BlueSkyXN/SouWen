# src/souwen/server/routes/admin navigation card

Type: Guardrail card.
This directory contains admin-only config, plugin, proxy, WARP and source-management endpoints.
Read `src/souwen/server/auth.py`, the target admin route, `tests/test_server/test_app.py`, plugin tests and relevant config docs before editing.
Read this card for any admin route, state-changing endpoint, secret-bearing response or management behavior.

## Why this is high-risk

- Admin endpoints can mutate runtime config, plugin state, HTTP backend/proxy settings and WARP behavior.
- Responses may contain credentials unless redaction is preserved.
- Permission mistakes can allow Guest/User callers to mutate admin state.

## Required before changes

- Confirm the endpoint requires Admin authorization through existing auth helpers.
- Identify all secrets or credentials crossing the route and keep redaction tests updated.
- For state changes, define failure behavior and rollback/partial-registration behavior.

## Do not

- Do not allow User or Guest to mutate admin state.
- Do not leave partially registered plugin handlers after failures.
- Do not broaden `SOUWEN_ADMIN_OPEN` beyond explicit local/CI debug semantics.
- Do not print full config, cookies, tokens or private URLs in logs/responses.

## Validation

- `pytest tests/test_server/test_app.py -v --tb=short`
- Plugin admin changes: `pytest tests/test_plugin_manager.py tests/test_plugin.py -v --tb=short`
