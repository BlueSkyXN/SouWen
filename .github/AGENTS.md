# .github navigation card

This directory contains GitHub Actions and repository automation.
Read the target workflow, `docs/testing.md`, and `docs/internal/development-branching.md` first.
Read this card for workflow jobs, permissions, CI gates, deployment or release automation.

## Local invariants

- PR gates should stay deterministic: ruff, pytest, registry/docs checks, panel build and profile runner.
- Live external checks, browsers, secrets and deploy smoke belong in dedicated workflows.
- Default workflow permission should be `contents: read`; expand only when the job needs it.

## Do not

- Do not print secrets, tokens, cookies or full environments.
- Do not make high-flake live external checks block every ordinary PR.
- Do not silently change deploy or release triggers.

## Validation

- Use affected script tests, for example `pytest tests/test_ci_profile_runner.py -v --tb=short`.
