# src/souwen/registry navigation card

Type: Domain card.
This directory is the source metadata and catalog source of truth.
Read `adapter.py`, `catalog.py`, `loader.py`, `views.py`, `capabilities.py`, `docs/source-catalog.md`, and `docs/adding-a-source.md` first.
Read this card for `SourceAdapter`, catalog shape, capability/default metadata, adapter validation or registry view changes.

## Local invariants

- CLI, REST API, doctor, Panel, docs and plugins must derive source facts from registry.
- Default sources come from `default_for`; high-risk or credential-heavy sources must not become defaults casually.
- Registry import must stay lazy and avoid importing every concrete provider client.
- External plugin autoload must remain disabled in deterministic docs/tests unless a test opts in.

## Do not

- Do not create parallel source lists or dispatcher dictionaries in other layers.
- Do not load heavy optional dependencies during registry import.
- Do not hide registry drift by editing generated docs by hand.

## Validation

- `pytest tests/registry/test_consistency.py tests/registry/test_catalog.py -v --tb=short`
- `python tools/gen_docs.py --check`
- `python scripts/ci/check_no_legacy_terms.py`
