# src/souwen/server/routes navigation card

Type: Domain card.
This directory contains host-only route wiring: `/api/v1/whoami` plus the read-only Admin router.
The canonical Search, LLM Search, Fetch, Provider catalog and probe routes live under
`src/souwen/delivery/api/`. Read `_common.py`, `whoami.py`, `src/souwen/server/schemas/`,
`docs/api-reference.md`, and matching tests first.

## Local invariants

- Host routes must preserve user/admin auth classification without entering the frozen target OpenAPI.
- Provider validation and target Data API behavior belong in delivery/modules/ProviderManager, not here.
- Host response structure changes need schema tests and Panel/docs consideration.

## Do not

- Do not bypass auth dependencies or expose an unauthenticated control-plane route.
- Do not hide internal failures behind successful empty responses.
- Do not put admin-only state mutation in public routes.

## Validation

- `pytest tests/test_server -v --tb=short`
- Target API changes: use the delivery contract tests and `server-contract` CI profile.
