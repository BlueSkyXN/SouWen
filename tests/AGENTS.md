# tests navigation card

Type: Guardrail card.
This directory contains deterministic pytest tests and fixtures.
Read `docs/testing.md`, `tests/conftest.py`, and the tested code's local `AGENTS.md` before broad test changes.
Read this card when adding/changing Python tests, fixtures, test isolation behavior or test package layout.

## Why this is high-risk

- Ordinary pytest is the deterministic gate for the repository.
- Tests must not depend on real network, browser runtimes, production secrets or the user's HOME config.
- Bad fixtures can hide regressions across CLI, server, registry and provider layers.

## Required before changes

- Read the local card for the code under test, not only this test card.
- Prefer monkeypatch, pytest-httpx and local fixtures for external responses.
- Put real runtime/browser/external smoke in `scripts/*_functional_check.py` or workflows.

## Do not

- Do not commit real secrets, cookies or account data.
- Do not make tests order-dependent or dependent on locally installed plugins.
- Do not let local `~/.config/souwen` influence outcomes.

## Validation

- Targeted: `pytest tests/path/test_file.py -v --tb=short`
- Full suite when needed: `pytest tests/ -v --tb=short`
