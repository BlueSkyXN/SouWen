# src/souwen/server/routes/admin navigation card

This is a high-risk admin API area for config, plugins, proxy, WARP and source management.
Read `server/auth.py`, target admin route, `tests/test_server/test_app.py`, and plugin tests before editing.
Read this card for any admin route or state-changing management behavior.

## Local invariants

- Every admin endpoint must require Admin authorization through existing auth helpers.
- Config and status responses must redact secrets.
- Plugin, WARP and HTTP backend state changes need clear failure behavior and safe defaults.

## Do not

- Do not allow User or Guest to mutate admin state.
- Do not leave partially registered plugin handlers after failures.
- Do not broaden `SOUWEN_ADMIN_OPEN` beyond explicit local/CI debug semantics.

## Validation

- `pytest tests/test_server/test_app.py -v --tb=short`
- Plugin admin changes: `pytest tests/test_plugin_manager.py tests/test_plugin.py -v --tb=short`
