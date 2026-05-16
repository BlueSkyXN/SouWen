# src/souwen/server/routes navigation card

This directory contains public REST route handlers.
Read `_common.py`, the target route, `server/schemas/`, and `docs/api-reference.md` first.
Read this card when changing non-admin route behavior, auth dependency use, route timeout or response shape.

## Local invariants

- Route code should parse requests, enforce auth/rate limits, set timeouts and call application APIs.
- Source/provider validation should come from registry, not static route lists.
- Public response structure changes need schema tests and docs consideration.

## Do not

- Do not bypass fetch SSRF, auth dependencies or rate limiting.
- Do not hide internal failures behind successful empty responses.

## Validation

- `pytest tests/test_server -v --tb=short`
