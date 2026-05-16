# src/souwen/web/bilibili navigation card

Type: Domain card.
This directory implements Bilibili-specific client behavior.
Read `client.py`, `wbi.py`, `models.py`, `tests/test_bilibili/`, and `src/souwen/registry/sources/video.py` first.
Read this card for WBI signing, cookie behavior, Bilibili risk-control/error mapping or models.

## Local invariants

- `bilibili_sessdata` is optional; anonymous paths should remain usable when upstream supports them.
- Cookie, WBI, risk-control and rate-limit failures should map to project exceptions or Bilibili-specific errors.
- Upstream response shape changes need fixture/mock coverage.
- Bilibili-specific behavior should remain isolated from generic web search clients.

## Do not

- Do not commit real account cookies or session data.
- Do not move Bilibili signing logic into generic web modules.
- Do not let tests depend on a live Bilibili account.

## Validation

- `pytest tests/test_bilibili -v --tb=short`
