# scripts/ci navigation card

This directory contains deterministic CI helper gates.
Read `run_profile.py`, `check_no_legacy_terms.py`, `.github/workflows/v2-ci.yml`, and `docs/testing.md` first.
Read this card for CI profile runner or helper gate changes.

## Local invariants

- `run_profile.py` does not install dependencies, download browsers or hit live external services.
- Profile commands should be deterministic and report JSON/Markdown when configured.
- New profiles must be discoverable by `--list-profiles` and covered by tests.

## Do not

- Do not put release deployment or secret-backed smoke behavior in the profile runner.
- Do not write repository files from profile checks.

## Validation

- `pytest tests/test_ci_profile_runner.py -v --tb=short`
- `python scripts/ci/run_profile.py --list-profiles`
