# src/souwen/cli navigation card

Type: Domain card.
This directory implements the Typer CLI command surface.
Read `__init__.py`, `_common.py`, the target command module, `cli.py`, and `tests/test_cli.py` before editing.
Read this card for CLI commands, flags, JSON output, help text, exit codes or command routing.

## Local invariants

- Source/provider lists should come from registry or application APIs.
- JSON output must stay machine-readable and avoid Rich-only formatting.
- New commands should remain reachable through `python cli.py --help` and `python -m souwen --help` where applicable.
- Failures that should be non-zero must not silently succeed.

## Do not

- Do not import heavy optional dependencies during CLI import.
- Do not hard-code source metadata that already lives in registry.
- Do not print secrets, cookies or private config values in command output.

## Validation

- `pytest tests/test_cli.py -v --tb=short`
- `python scripts/ci/run_profile.py --profile minimal`
