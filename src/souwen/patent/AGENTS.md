# src/souwen/patent navigation card

This directory implements patent source clients.
Read `src/souwen/registry/sources/patent.py`, `src/souwen/models.py`, and `tests/test_patent/` first.
Read this card when changing patent providers, OAuth credentials, parsing or registry mappings.

## Local invariants

- Patent outputs should be normalized and keep useful `raw` data for diagnostics.
- OAuth and multi-field credential sources must declare every required credential in registry.
- Scraper-style patent sources should use `BaseScraper`.

## Do not

- Do not push patent parameter translation into `souwen.search`; use `MethodSpec`.
- Do not require real patent platform accounts for unit tests.

## Validation

- `pytest tests/test_patent -v --tb=short`
- `pytest tests/registry/test_consistency.py -v`
