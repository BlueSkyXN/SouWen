# scripts navigation card

This directory contains functional checks, smoke helpers and runtime scripts.
Read `docs/testing.md`, `_functional_common.py`, target script and related workflow before editing.
Read this card for non-pytest checks, reports, outcomes or smoke script behavior.

## Local invariants

- Functional scripts must run outside pytest and support JSON/Markdown reports when appropriate.
- Outcome semantics are `PASS`, `WARN`, `FAIL`, `SKIP`.
- Runtime installation belongs in workflow steps, not hidden inside Python scripts.

## Do not

- Do not move live external checks into ordinary pytest.
- Do not return success for required failures.

## Validation

- `pytest tests/test_functional_common.py tests/test_plugin_functional_check.py -v --tb=short`
