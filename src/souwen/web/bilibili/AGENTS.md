# src/souwen/web/bilibili navigation card

This directory implements Bilibili-specific client behavior.
Read `client.py`, `wbi.py`, `models.py`, `tests/test_bilibili/`, and `registry/sources/video.py` first.
Read this card for WBI signing, cookie behavior, Bilibili error mapping or models.

## Local invariants

- `bilibili_sessdata` is optional; anonymous paths should remain usable when supported upstream.
- Cookie, WBI, risk-control and rate-limit failures should map to project exceptions or Bilibili-specific errors.
- Upstream response changes need fixture/mock coverage.

## Do not

- Do not commit real account cookies.
- Do not scatter Bilibili-specific logic into generic web search.

## Validation

- `pytest tests/test_bilibili -v --tb=short`
