# docs navigation card

Type: Domain card.
This directory contains user docs, contributor docs, architecture notes, ADRs, API docs and generated source catalog docs.
Read `docs/README.md`, the relevant topic docs, `tools/gen_docs.py`, and behavior tests before editing generated or behavior-linked docs.
Read this card for docs changes, generated docs, API docs or behavior changes that require docs updates.

## Local invariants

- Commands, config names, API fields and paths must match repository files.
- `docs/data-sources.md` is generated from registry by `tools/gen_docs.py`.
- ADR/internal docs record decisions; tests still verify behavior.
- API docs should stay aligned with `src/souwen/server/schemas/` and route tests.

## Do not

- Do not invent APIs, commands, config fields or deployment features.
- Do not manually edit generated source tables to hide registry drift.
- Do not document secrets, real tokens, cookies or private service URLs.

## Validation

- `python tools/gen_docs.py --check`
- Generated-doc tests: `pytest tests/test_gen_docs.py -v --tb=short`
- API docs impact: `pytest tests/test_server/test_api_reference_routes.py -v --tb=short`
