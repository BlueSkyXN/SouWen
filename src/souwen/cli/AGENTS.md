# src/souwen/cli navigation card

This directory implements the Typer CLI.
Read `__init__.py`, `_common.py`, `cli.py`, and `tests/test_cli.py` before editing.
Read this card for CLI commands, flags, JSON output, help text or exit behavior.

## Local invariants

- Source/provider lists should come from registry or application APIs.
- JSON output must stay machine-readable.
- New commands should be visible through both `python cli.py --help` and `python -m souwen --help`.

## Do not

- Do not import heavy optional dependencies during CLI import.
- Do not silently succeed after command failures that should be non-zero.

## Validation

- `pytest tests/test_cli.py -v --tb=short`
- `python scripts/ci/run_profile.py --profile minimal`
