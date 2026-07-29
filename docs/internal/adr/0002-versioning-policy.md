# ADR 0002: Public Release Version

**Status**: Accepted
**Date**: 2026-05-08; revised 2026-07-29
**Scope**: Souwen v2rc4 release candidate on `main`

## Context

SouWen v2 is a breaking architecture line, not a compatibility continuation of
the previous public surface. Earlier SouWen versions, changelog entries,
workflow comments, and deployment assets are already visible in the repository
history, so hiding that lineage behind a new `1.0.0rc1` number would make the
release story less clear rather than more productized.

RC1 established the breaking v2 lineage. RC2 completed the first published
target-only release and HFS promotion at source `19871b1bbae8f2af65fdd0bb418f6275dc4061d0`.
RC3 completed the expanded release/HFS evidence chain at source
`94e94d13b1cf72fbaea6e85f8b121c910780ab1d`. All three tags remain immutable
historical baselines; later release-candidate work must use a new version rather
than moving an existing tag.

## Decision

The current release candidate is **Souwen v2rc4**. It is not the `2.0.0` GA.

The version surfaces are:

- Product and GitHub Release display name: `Souwen v2rc4`
- Python package, runtime, OpenAPI artifact, health/readiness and evidence version:
  `2.0.0rc4`
- README badges and API/deployment examples: `2.0.0rc4`
- Panel package version: `2.0.0-rc4`
- Git tag: `v2.0.0rc4`
- API major: `2`
- Binary artifact prefix: `souwen-server-2.0.0rc4-*`
- Changelog release heading: `v2.0.0rc4`

The tag and GitHub Release may be created only after the RC4 exact-candidate
release gates, HFS validation, manifest/checksum/attestation and asset readback
all pass. RC4 completion does not authorize an automatic `2.0.0` GA tag.

## Consequences

- Public docs should present this line as Souwen v2rc4, not as
  an undecided first-public-release experiment.
- RC1, RC2 and RC3 values may remain only in clearly historical baseline text. Runtime,
  generated artifacts, current examples, manifests and new release material must
  use the RC4 values above.
- The RC is not a final release by metadata alone; clean install, server/auth,
  Panel, docs walk-through, external smoke, and at least one target release path
  still need release validation before tag or publishing decisions.
- `publish=true` remains fail closed unless the exact four PyInstaller Server
  bundles, release evidence, HFS promotion, checksums, and attestations all pass
  on the same candidate SHA.
- PyPI publishing remains out of scope for this release line unless explicitly
  reintroduced later.
