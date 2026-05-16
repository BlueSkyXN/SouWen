# src/souwen/registry navigation card

This directory is the source metadata and catalog source of truth.
Read `adapter.py`, `catalog.py`, `views.py`, `docs/source-catalog.md`, and `docs/adding-a-source.md` first.
Read this card for SourceAdapter, Source Catalog, capability, default source or registry view changes.

## Key files

- `adapter.py`: `SourceAdapter`, `MethodSpec` and validation.
- `catalog.py`: public catalog projection.
- `views.py`: registry queries and external plugin views.

## Local invariants

- CLI, REST API, doctor, Panel and generated docs must derive source facts from registry.
- Default sources come from `default_for`; high-risk sources must not be defaults.
- Registry import must stay lazy and avoid importing every client.

## Do not

- Do not create parallel source lists or dispatcher dicts.
- Do not load external plugins or heavy optional dependencies during registry import.

## Validation

- `pytest tests/registry/test_consistency.py tests/registry/test_catalog.py -v --tb=short`
- `python tools/gen_docs.py --check`
