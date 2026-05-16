# src/souwen/paper navigation card

This directory implements paper source clients.
Read `src/souwen/models.py`, `src/souwen/registry/sources/paper.py`, and the relevant `tests/test_paper/` file first.
Read this card when changing paper providers, credentials, parsing or result normalization.

## Local invariants

- Return normalized `PaperResult`, `Author` and `SearchResponse` objects.
- Official/API clients should reuse `SouWenHttpClient`; OAuth clients should reuse `OAuthClient`.
- API keys should resolve through config helpers so channel-level overrides work.

## Do not

- Do not maintain paper default source lists here.
- Do not expose upstream raw response shapes as public result schema.

## Validation

- `pytest tests/test_paper -v --tb=short`
- `pytest tests/registry/test_consistency.py -v`
