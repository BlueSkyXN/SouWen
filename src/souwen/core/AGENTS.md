# src/souwen/core navigation card

This directory is the shared Python platform layer.
Read `http_client.py`, `scraper/base.py`, `exceptions.py`, `concurrency.py`, and `docs/anti-scraping.md` first.
Read this card for low-level HTTP, retry, OAuth, scraping, rate limit, session cache or concurrency changes.

## Key files

- `http_client.py`: `SouWenHttpClient` and `OAuthClient`.
- `scraper/base.py`: shared scraper backend, TLS fingerprint and polite delay.
- `exceptions.py`: shared exception taxonomy.

## Local invariants

- API clients should reuse `SouWenHttpClient`; scraper clients should reuse `BaseScraper`.
- Keep status-code mapping to `AuthError`, `RateLimitError`, `SourceUnavailableError` stable.
- Concurrency primitives must remain safe across multiple event loops.

## Do not

- Do not copy proxy/retry/fingerprint logic into individual source clients.
- Do not make core depend on CLI, Server, Panel or concrete route modules.

## Validation

- `pytest tests/test_rate_limiter.py tests/test_fingerprint.py tests/test_session_cache.py -v --tb=short`
- For scraper/fetch impact: `pytest tests/test_web/test_fetch.py -v --tb=short`
