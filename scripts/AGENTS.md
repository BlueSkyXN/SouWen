# scripts navigation card

Type: Domain card.
This directory contains functional checks, smoke helpers, CI-profile support code and runtime shell scripts.
Read `docs/testing.md`, `_functional_common.py`, the target script and related workflow before editing.
Read this card for non-pytest checks, reports, outcome semantics, runtime smoke behavior or shell script behavior.

## Local invariants

- Functional scripts must run outside pytest and support JSON/Markdown reports when appropriate.
- Outcome semantics are `PASS`, `WARN`, `FAIL`, `SKIP`.
- Runtime installation belongs in workflow steps, not hidden inside Python scripts.
- Scripts that hit live services must make that dependency explicit.

## Do not

- Do not move live external checks into ordinary pytest.
- Do not return success for required failures.
- Do not write generated reports into tracked files unless the workflow explicitly expects that.

## Validation

- `pytest tests/test_functional_common.py tests/test_plugin_functional_check.py -v --tb=short`
- For CI profile logic, read `scripts/ci/AGENTS.md`.
