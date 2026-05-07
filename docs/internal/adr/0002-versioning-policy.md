# ADR 0002: Versioning Policy Before Public Release

**Status**: Accepted  
**Date**: 2026-05-07  
**Scope**: SouWen `v2-dev`

## Context

The repository currently uses `2.0.0rc1` on `v2-dev`. That version reflects the internal migration line, but the final public release number should match how SouWen is presented externally.

The project should avoid keeping the version decision open across every follow-up PR. The decision rule should be written down now and resolved before public documentation is finalized.

## Decision

The release version will be finalized before the public documentation rewrite phase.

Use `1.0.0rc1` if this line is treated as SouWen's first formal public architecture release:

- no meaningful external user base depends on earlier release numbers;
- earlier versions are considered internal development milestones;
- public docs are written as the first formal product documentation set.

Keep `2.0.0rc1` if the project intentionally preserves the internal history as public version semantics:

- earlier public packages, docs, or deployments should remain part of the visible release lineage;
- users should understand the current architecture as a breaking major release.

## Required Follow-Up

Before the public docs productization PR merges, update the decision record with the final selected version and align:

- `pyproject.toml`
- `src/souwen/__init__.py`
- README badges
- `CHANGELOG.md`
- API examples that show version strings
- release workflow notes

## Consequences

- PRs before the public docs rewrite should not churn version numbers.
- PR descriptions should avoid promising either version until the final decision is made.
- Internal docs may keep `v2-dev` as the branch name regardless of final package version.
