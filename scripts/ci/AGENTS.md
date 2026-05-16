# scripts/ci navigation card

Type: Guardrail card.
This directory contains deterministic CI helper gates and the local profile runner.
Read `run_profile.py`, `check_no_legacy_terms.py`, `.github/workflows/v2-ci.yml`, and `docs/testing.md` first.
Read this card for CI profile runner semantics, helper gates, deterministic report behavior or CI command changes.

## Why this is high-risk

- CI helper changes can silently weaken merge gates.
- `run_profile.py` is intended to be deterministic and must not install dependencies or hit live services.
- Profile output is consumed by workflows and reports.

## Required before changes

- Confirm whether the behavior belongs in pytest, a CI profile, a functional script or a workflow step.
- New profiles must be discoverable by `--list-profiles` and covered by tests.
- Keep write behavior explicit; check/list modes should not mutate repository files.

## Do not

- Do not put release deployment or secret-backed smoke behavior in the profile runner.
- Do not download browsers, install packages or call live external services from deterministic profiles.
- Do not write repository files from profile checks.

## Validation

- `pytest tests/test_ci_profile_runner.py -v --tb=short`
- `python scripts/ci/run_profile.py --list-profiles`
