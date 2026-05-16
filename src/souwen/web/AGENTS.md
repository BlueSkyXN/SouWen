# src/souwen/web navigation card

This directory implements web/search/fetch/archive/social/video provider clients.
Read `fetch.py`, `search.py`, `core/scraper/base.py`, `docs/anti-scraping.md`, and `tests/test_web/` first.
Read this card for web providers, fetch providers, SSRF checks, scraping behavior or provider routing.

## Local invariants

- Fetch must preserve SSRF checks for private, loopback, link-local and reserved targets.
- Missing optional dependencies or credentials should degrade with clear errors, not crash aggregation.
- API providers should use `SouWenHttpClient`; scraper providers should use `BaseScraper`.
- New fetch providers must align handler registration, registry metadata, route validation and tests.

## Do not

- Do not let ordinary pytest hit live search engines or social platforms.
- Do not bypass URL safety checks except in explicit tests/internal paths.

## Validation

- `pytest tests/test_web -v --tb=short`
- Fetch changes: `pytest tests/test_fetch_handlers.py tests/test_web/test_fetch.py -v --tb=short`
