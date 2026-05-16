# src/souwen/core navigation card

Type: Domain card.
This directory is the shared Python platform layer for HTTP, OAuth, retry, parsing, scraper base, rate limiting and concurrency.
Read `http_client.py`, `scraper/base.py`, `exceptions.py`, `concurrency.py`, `retry.py`, and `docs/anti-scraping.md` before changing shared behavior.
Read this card for low-level client behavior, retry/fingerprint/session/cache, scraper base, exception mapping or concurrency changes.

## Local invariants

- API clients should reuse `SouWenHttpClient`; scraper clients should reuse `BaseScraper`.
- OAuth flows should reuse `OAuthClient` and map auth failures to project exceptions.
- Status-code/error mapping to `AuthError`, `RateLimitError` and `SourceUnavailableError` must stay stable.
- Concurrency helpers must remain safe across multiple event loops and isolated tests.

## Do not

- Do not copy proxy, retry, fingerprint or polite-delay logic into individual provider clients.
- Do not make `core` depend on CLI, Server, Panel, MCP or route modules.
- Do not let ordinary tests perform live network requests from core helpers.

## Validation

- `pytest tests/test_rate_limiter.py tests/test_fingerprint.py tests/test_session_cache.py -v --tb=short`
- Fetch/scraper impact: `pytest tests/test_web/test_fetch.py -v --tb=short`
