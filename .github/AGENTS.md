# .github navigation card

Type: Guardrail card.
This directory contains GitHub Actions, repository prompts, labeler config and dependency automation.
Read the target workflow/config, `docs/testing.md`, and `docs/internal/development-branching.md` before editing.
Read this card for workflow jobs, permissions, CI gates, deploy/release triggers, labels, Dependabot or AI prompt automation.

## Why this is high-risk

- Workflow changes can weaken merge gates, leak secrets or trigger deployments.
- Prompts and automation influence reviewer/agent behavior across PRs.
- GitHub permissions should stay least-privilege.

## Local invariants

- `.github/prompts/` is AI workflow control-plane content, not ordinary docs.
- AI workflows must materialize trusted prompts from `github.workflow_sha` or a
  trusted base ref; never from PR head files.
- Commit-capable AI automation must keep the pre-commit guard blocking staged
  `.github/workflows/` and `.github/prompts/` changes unless that trust boundary
  is explicitly redesigned.

## Required before changes

- Confirm which workflow/event path is affected: PR gate, scheduled smoke, release/build, deploy or AI automation.
- Keep deterministic PR gates separate from live external smoke.
- Expand `permissions` only for jobs that need the additional scope.
- For AI workflows, review the matching prompt and comment/summary publication
  path with the workflow change.

## Do not

- Do not print secrets, tokens, cookies or full environments.
- Do not make high-flake live external checks block every ordinary PR.
- Do not silently change deploy or release triggers.
- Do not add write permissions globally when a single job can scope them.
- Do not remove owner/environment gates from manual AI workflows without an
  equally strict replacement.

## Validation

- Use affected script tests, for example `pytest tests/test_ci_profile_runner.py -v --tb=short`.
- For panel CI changes, `cd panel && npm run build` is the local equivalent of typecheck/build.
