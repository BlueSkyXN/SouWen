# src/souwen/paper navigation card

Type: Domain card.
This directory implements paper provider clients and paper result normalization.
Read `core.py`, the target provider module, `src/souwen/models.py`, `src/souwen/registry/sources/paper.py`, and matching `tests/test_paper/` files first.
Read this card when changing paper providers, credentials, parsing, PDF/fulltext handling or result normalization.

## Local invariants

- Return normalized `PaperResult`, `Author` and `SearchResponse` objects.
- Official/API clients should reuse `SouWenHttpClient`; OAuth clients should reuse `OAuthClient`.
- API keys and channel overrides should resolve through config helpers.
- Provider quirks belong in provider modules, while registry parameter mapping belongs in `registry/sources/paper.py`.

## Do not

- Do not maintain paper default source lists here.
- Do not expose upstream raw response shapes as public result schema.
- Do not make ordinary tests require real paper API keys or live network.

## Validation

- `pytest tests/test_paper -v --tb=short`
- Registry impact: `pytest tests/registry/test_consistency.py -v --tb=short`
