# tests/registry navigation card

Type: Domain card.
This directory tests registry and Source Catalog invariants.
Read `test_consistency.py`, `test_catalog.py`, `src/souwen/registry/`, `src/souwen/registry/sources/`, and `docs/adding-a-source.md` first.
Read this card when changing registry tests, catalog projections or source metadata validation.

## Local invariants

- Tests should identify the broken invariant instead of only snapshotting large payloads.
- Source additions must cover loader, method mapping, param map, credentials, defaults and catalog projection.
- External plugin autoload must stay disabled or isolated for checked-in expectations.
- Generated docs checks should fail on registry drift instead of masking it.

## Do not

- Do not make expectations depend on locally installed plugins.
- Do not bless a registry change by weakening invariants without documenting the behavior change.

## Validation

- `pytest tests/registry -v --tb=short`
- `python tools/gen_docs.py --check`
