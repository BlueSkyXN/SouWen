# src/souwen/web navigation card

Type: Domain card.
This directory implements web search, fetch, archive, social, developer, video and aggregation clients.
Read `fetch.py`, `search.py`, the target provider module, `src/souwen/core/scraper/base.py`, `docs/anti-scraping.md`, and matching `tests/test_web/` files first.
Read this card for web providers, fetch providers, SSRF checks, scraping behavior, optional dependency handling or provider routing.

## Local invariants

- Fetch must preserve SSRF checks for private, loopback, link-local and reserved targets.
- Missing optional dependencies or credentials should produce clear errors or aggregation skips, not import-time crashes.
- API providers should use `SouWenHttpClient`; scraper/browser-like providers should use `BaseScraper` or the established fetcher abstraction.
- New fetch providers must align handler registration, registry metadata, route validation and tests.

## Do not

- Do not let ordinary pytest hit live search engines, social platforms or browser runtimes.
- Do not bypass URL safety checks except in explicit tests/internal paths.
- Do not scatter provider selection lists outside registry metadata.

## Validation

- `pytest tests/test_web -v --tb=short`
- Fetch changes: `pytest tests/test_fetch_handlers.py tests/test_web/test_fetch.py -v --tb=short`
