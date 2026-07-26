# src/souwen/server/schemas navigation card

Type: Domain card.
This directory defines host-only Admin/common response schemas. Canonical target Data API schemas are
owned by `src/souwen/delivery/api/` and generated from the frozen OpenAPI artifact.
Read the target schema, route, `docs/api-reference.md` and server contract tests first.

## Local invariants

- Host schema changes may require route, Panel and docs updates.
- Defaults, aliases, ranges and optional fields must match route behavior and Panel expectations.
- Shared error responses must remain compatible with `ErrorResponse`.
- Schema modules must stay side-effect free.

## Do not

- Do not put network, filesystem or config side effects inside schema definitions.
- Do not duplicate canonical target DTOs in this directory.
- Do not use schemas to bypass auth, rate-limit or SSRF checks.

## Validation

- `pytest tests/test_server/test_openapi_contract.py tests/test_server -v --tb=short`
- Panel type impact: `cd panel && npm run build`
