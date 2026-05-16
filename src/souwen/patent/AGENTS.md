# src/souwen/patent navigation card

Type: Domain card.
This directory implements patent provider clients and patent result normalization.
Read the target provider module, `src/souwen/registry/sources/patent.py`, `src/souwen/models.py`, and matching `tests/test_patent/` files first.
Read this card when changing patent providers, OAuth/multi-field credentials, scraping behavior, parsing or registry mappings.

## Local invariants

- Patent outputs should be normalized while keeping useful `raw` data for diagnostics.
- OAuth and multi-field credential sources must declare every required credential in registry metadata.
- Scraper-style patent sources should use `BaseScraper`.
- Parameter translation belongs in `MethodSpec`, not in `souwen.search`.

## Do not

- Do not require real patent platform accounts for unit tests.
- Do not copy scraper/fingerprint behavior from `core`.
- Do not put provider credentials into examples or docs as real secrets.

## Validation

- `pytest tests/test_patent -v --tb=short`
- Registry impact: `pytest tests/registry/test_consistency.py -v --tb=short`
