# tests navigation card

This directory contains deterministic pytest tests.
Read `docs/testing.md` and `tests/conftest.py` before broad test changes.
Read this card when adding or changing Python tests, fixtures or test isolation.

## Local invariants

- Default tests must be offline, deterministic and independent of real HOME config.
- Use monkeypatch, pytest-httpx and local fixtures for external responses.
- Real browser/runtime/external-service checks belong in `scripts/*_functional_check.py` or workflows.

## Do not

- Do not commit real secrets, cookies or account data.
- Do not make tests order-dependent.
- Do not let local `~/.config/souwen` influence outcomes.

## Validation

- `pytest tests/path/test_file.py -v --tb=short`
- Full suite when needed: `pytest tests/ -v --tb=short`
