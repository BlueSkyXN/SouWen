# docs navigation card

This directory contains user, contributor, architecture and deployment documentation.
Read `docs/README.md`, relevant topic docs, and `tools/gen_docs.py` before editing generated source docs.
Read this card for docs changes or behavior changes that require docs updates.

## Local invariants

- Commands, config names, API fields and paths must match repository files.
- `docs/data-sources.md` is generated from registry by `tools/gen_docs.py`.
- ADR/internal docs record decisions; tests still verify behavior.

## Do not

- Do not invent APIs, commands, config fields or deployment features.
- Do not manually edit generated source tables to hide registry drift.

## Validation

- `python tools/gen_docs.py --check`
- Generated-doc tests: `pytest tests/test_gen_docs.py -v --tb=short`
