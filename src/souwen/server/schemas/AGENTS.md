# src/souwen/server/schemas navigation card

This directory defines REST request/response schemas.
Read the target schema file, route using it, `docs/api-reference.md`, and `tests/test_server/test_openapi_contract.py` first.
Read this card when changing API fields, validation constraints, aliases or error schema.

## Local invariants

- Schema changes are API contract changes.
- Defaults, aliases and ranges must match route behavior and Panel expectations.
- Keep shared error responses compatible with `ErrorResponse`.

## Do not

- Do not put network, filesystem or config side effects inside schema definitions.
- Do not remove public fields without updating tests and clients.

## Validation

- `pytest tests/test_server/test_openapi_contract.py tests/test_server -v --tb=short`
