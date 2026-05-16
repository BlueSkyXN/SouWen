# src/souwen/server/schemas navigation card

Type: Domain card.
This directory defines REST request/response schemas and OpenAPI-facing contracts.
Read the target schema file, the route using it, `docs/api-reference.md`, `panel/src/core/types/api.ts`, and OpenAPI contract tests first.
Read this card when changing API fields, validation constraints, aliases, defaults or error schema.

## Local invariants

- Schema changes are API contract changes and may require route, panel and docs updates.
- Defaults, aliases, ranges and optional fields must match route behavior and Panel expectations.
- Shared error responses must remain compatible with `ErrorResponse`.
- Schema modules must stay side-effect free.

## Do not

- Do not put network, filesystem or config side effects inside schema definitions.
- Do not remove public fields without updating tests and clients.
- Do not use schemas to bypass auth, rate-limit or SSRF checks.

## Validation

- `pytest tests/test_server/test_openapi_contract.py tests/test_server -v --tb=short`
- Panel type impact: `cd panel && npm run build`
