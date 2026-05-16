# tests/registry navigation card

This directory tests registry and Source Catalog invariants.
Read `test_consistency.py`, `test_catalog.py`, `src/souwen/registry/`, and `docs/adding-a-source.md` first.
Read this card when changing registry tests or source metadata validation.

## Local invariants

- Tests should identify the broken invariant, not only snapshot large payloads.
- Source additions must cover loader, method, param map, credentials, defaults and catalog projection.
- External plugin autoload must stay disabled or isolated for checked-in expectations.

## Do not

- Do not make expectations depend on locally installed plugins.

## Validation

- `pytest tests/registry -v --tb=short`
- `python tools/gen_docs.py --check`
