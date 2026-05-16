# ADR 0002: Public Release Version

**Status**: Accepted
**Date**: 2026-05-08
**Scope**: SouWen v2 release candidate on `main`

## Context

SouWen v2 is a breaking architecture line, not a compatibility continuation of
the previous public surface. Earlier SouWen versions, changelog entries,
workflow comments, and deployment assets are already visible in the repository
history, so hiding that lineage behind a new `1.0.0rc1` number would make the
release story less clear rather than more productized.

The release candidate metadata is already aligned on `2.0.0rc1` for Python and
`2.0.0-rc1` for the Panel package. Keeping that version avoids unnecessary churn
while preserving the intended "breaking v2 candidate" semantics.

## Decision

SouWen v2 will use `2.0.0rc1` as the release candidate version.

The version surfaces are:

- Python package / runtime version: `2.0.0rc1`
- README badges and API examples: `2.0.0rc1`
- Panel package version: `2.0.0-rc1`
- Changelog release heading: `v2.0.0rc1`

A future release tag may use the normal Git tag form `v2.0.0rc1` after RC smoke
and release validation complete.

## Consequences

- Public docs should present this line as SouWen's v2 release candidate, not as
  an undecided first-public-release experiment.
- Follow-up PRs must not reopen the `1.0.0rc1` versus `2.0.0rc1` decision
  unless the release strategy itself changes.
- The RC is not a final release by metadata alone; clean install, server/auth,
  Panel, docs walk-through, external smoke, and at least one target release path
  still need release validation before tag or publishing decisions.
- PyPI publishing remains out of scope for this release line unless explicitly
  reintroduced later.
