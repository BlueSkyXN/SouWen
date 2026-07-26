# src/souwen/server/routes/admin navigation card

Type: Guardrail card.
This directory contains authenticated, read-only Admin config, doctor and ping endpoints.
Read `src/souwen/server/auth.py`, the target admin route,
`tests/test_server/test_openapi_contract.py` and relevant config docs before editing.

## Why this is high-risk

- Config projections may contain credentials unless redaction is preserved.
- Doctor output projects Provider v2 eligibility and must not perform live network probes.
- Permission mistakes can expose Admin-only deployment state to Guest/User callers.

## Required before changes

- Confirm the endpoint requires Admin authorization through existing auth helpers.
- Identify all secrets or credentials crossing the route and keep redaction tests updated.
- Keep Admin routes read-only; runtime mutation belongs in deployment/configuration management.

## Do not

- Do not add config/proxy/WARP/source mutation endpoints.
- Do not allow User or Guest to read Admin state.
- Do not broaden `SOUWEN_ADMIN_OPEN` beyond explicit local/CI debug semantics.
- Do not print full config, cookies, tokens or private URLs in logs/responses.

## Validation

- `pytest tests/test_server/test_openapi_contract.py tests/test_hf_space_smoke.py -v --tb=short`
