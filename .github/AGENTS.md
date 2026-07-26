# .github navigation card

Type: Guardrail card.
This directory contains GitHub Actions, labeler config and dependency automation.
Read the target workflow/config, `docs/testing.md`, and `docs/internal/development-branching.md` before editing.
Read this card for workflow jobs, permissions, CI gates, deploy/release triggers, labels or Dependabot.

## Why this is high-risk

- Workflow changes can weaken merge gates, leak secrets or trigger deployments.
- GitHub permissions should stay least-privilege.

## Required before changes

- Confirm which workflow/event path is affected: PR gate, scheduled smoke, release/build or deploy.
- Keep deterministic PR gates separate from live external smoke.
- Expand `permissions` only for jobs that need the additional scope.

## Do not

- Do not print secrets, tokens, cookies or full environments.
- Do not make high-flake live external checks block every ordinary PR.
- Do not silently change deploy or release triggers.
- Do not add write permissions globally when a single job can scope them.

## Validation

- Use affected script tests, for example `pytest tests/test_ci_profile_runner.py -v --tb=short`.
- For panel CI changes, `cd panel && npm run build` is the local equivalent of typecheck/build.
