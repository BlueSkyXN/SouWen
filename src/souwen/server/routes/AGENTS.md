# src/souwen/server/routes navigation card

Type: Domain card.
This directory contains public non-admin REST route handlers.
Read `_common.py`, the target route, `src/souwen/server/schemas/`, `docs/api-reference.md`, and matching `tests/test_server/` files first.
Read this card when changing non-admin route behavior, auth dependency use, route timeout, provider validation or response wrapping.

## Local invariants

- Route code should parse requests, enforce auth/rate limits, set timeouts and call application APIs.
- Source/provider validation should come from registry metadata, not static route lists.
- Public response structure changes need schema tests and docs/API contract consideration.
- Fetch routes must preserve SSRF protection and route-level validation.

## Do not

- Do not bypass auth dependencies, fetch SSRF checks or rate limiting.
- Do not hide internal failures behind successful empty responses.
- Do not put admin-only state mutation in public routes.

## Validation

- `pytest tests/test_server -v --tb=short`
- Fetch route changes: `pytest tests/test_server/test_fetch_route.py -v --tb=short`
