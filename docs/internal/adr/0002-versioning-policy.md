# ADR 0002: Public Release Version

**Status**: Accepted
**Date**: 2026-05-08; revised 2026-07-24
**Scope**: Souwen v2rc2 release candidate on `main`

## Context

SouWen v2 is a breaking architecture line, not a compatibility continuation of
the previous public surface. Earlier SouWen versions, changelog entries,
workflow comments, and deployment assets are already visible in the repository
history, so hiding that lineage behind a new `1.0.0rc1` number would make the
release story less clear rather than more productized.

RC1 established the breaking v2 lineage but did not become the final candidate.
It remains an immutable historical and deployed baseline: Python/runtime
`2.0.0rc1`, Panel `2.0.0-rc1`, and candidate tag spelling `v2.0.0rc1`. The next
usable candidate must not continue reporting those values as its current identity.

## Decision

The current release candidate is **Souwen v2rc2**. It is not the `2.0.0` GA.

The version surfaces are:

- Product and GitHub Release display name: `Souwen v2rc2`
- Python package, runtime, OpenAPI artifact, health/readiness and evidence version:
  `2.0.0rc2`
- README badges and API/deployment examples: `2.0.0rc2`
- Panel package version: `2.0.0-rc2`
- Git tag: `v2.0.0rc2`
- API major: `2`
- Binary artifact prefix: `souwen-server-2.0.0rc2-*`
- Changelog release heading: `v2.0.0rc2`

The tag and GitHub Release may be created only after the RC2 exact-candidate
release gates, HFS validation, manifest/checksum/attestation and asset readback
all pass. RC2 completion does not authorize an automatic `2.0.0` GA tag.

## Consequences

- Public docs should present this line as Souwen v2rc2, not as
  an undecided first-public-release experiment.
- RC1 values may remain only in clearly historical baseline text. Runtime,
  generated artifacts, current examples, manifests and new release material must
  use the RC2 values above.
- The RC is not a final release by metadata alone; clean install, server/auth,
  Panel, docs walk-through, external smoke, and at least one target release path
  still need release validation before tag or publishing decisions.
- Until Phase 8 replaces the inherited 24-binary CLI/Nuitka matrix with exactly
  four PyInstaller server bundles, `publish=true` must remain fail closed.
- PyPI publishing remains out of scope for this release line unless explicitly
  reintroduced later.
