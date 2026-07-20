# SouWen v2 Branching and Release Gates

SouWen v2 is now merged back to `main` as the current release candidate line.
Future fixes for the v2 public surface should target `main`.

## Branch Roles

```text
main
  Active v2 release-candidate line and default development target.

v2/*
  Short-lived implementation branches. Each branch should live in its own
  worktree and target the active base selected for that task.
```

## Worktree Flow

Create implementation branches from the latest `origin/main` by default:

```bash
git fetch origin
git worktree add ../SouWen-fix-release-docs -b fix/release-docs origin/main
```

Open pull requests to `main` unless the maintainer explicitly asks for another
base:

```bash
gh pr create --base main --head fix/release-docs
```

## Completed v2 Migration Order

The v2 mergeback was staged through these historical implementation slices:

1. `v2/00-bootstrap`: v2 branch policy, v2 CI entry, AI workflow quarantine.
2. `v2/01-registry-meta`: registry package split and `registry/meta.py`.
3. `v2/02-search-facade-removal`: search/fetch consolidation and facade deletion.
4. `v2/03-core-path-migration`: core imports, scraper removal, top-level stub deletion.
5. `v2/04-reexport-cleanup`: domain and web re-export directory deletion.
6. `v2/05-docs-tests-release`: docs, tests, package surface, and `2.0.0-rc1`.
7. `v2/06-fetch-docs-polish`: `fetch_content` providers 参数口径收敛。
8. `v2/07-review-hardening`: review 发现项修复、import/wheel surface gate 补强。
9. `v2/08-release-cd-readiness`: v2 发布前 CI gate 和 CD 边界收口。

## CI/CD Policy

`CI` remains the broad default gate for `main`. `V2 CI` is retained as the
dedicated v2 public-surface gate and runs on `main`.

`V2 CI` must cover:

- bootstrap/import/wheel surface gate: registry/docs tests, generated docs
  freshness, removed v1 import-surface leak check, and required v2 module check.
- full pytest matrix: Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu, plus Python
  3.11 on macOS and Windows.
- `pro-cli` + `basic-cli` profile: local API surface tests and CLI smoke through
  `scripts/ci/run_profile.py`; legacy `server` / `minimal` aliases remain
  accepted during transition.
- `full-cli` runtime profile: `edition-full` core source, doctor, plugin, and
  fetch handler import surface through `scripts/ci/run_profile.py`, plus feature
  matrix declarations for full-only providers. The legacy `full` alias remains
  accepted during transition. The mutually exclusive `crawl4ai` / `scrapling`
  browser runtime variants stay in their dedicated functional gates.
- plugin profile: example plugin install, plugin contract tests, and entry point
  discovery through `scripts/ci/run_profile.py`.
- panel build: TypeScript check, Vitest, single-file panel build, and
  `src/souwen/server/panel.html` artifact validation.

External smoke, HF Space local preflight, PyInstaller/Nuitka builders, and
secret-backed checks keep their dedicated reusable/manual/schedule entrypoints.
They should not be folded into every ordinary PR. Remote HFS promotion and
GitHub publication are coordinated only by `release-candidate.yml`.

PyInstaller and Nuitka release artifacts use the three CLI edition profiles:
`basic-cli`, `pro-cli`, and `full-cli`. The manual workflow inputs keep legacy
aliases for transition only: `cli` maps to `basic-cli`, `server` maps to
`pro-cli`, and `full` maps to `full-cli`.

## Central release-candidate flow

`.github/workflows/release-candidate.yml` is the only release orchestrator. Run
it from the current `main` workflow revision with an exact 40-character
`candidate_sha` and matching prerelease version.

1. Commit and push the candidate branch, open one integration PR to `main`, and
   require `CI / aggregate` plus `V2 CI / v2 release readiness summary` remotely.
2. After the central workflow exists on trusted `main`, run it with
   `publish=false` and `deploy_hfs=false`. The candidate may be a descendant of
   current `origin/main`; this run has no external release/deploy write.
3. Accept **RC-ready** only when all 15 always-required gates pass on the exact
   candidate and the evidence bundle inventory/checksums agree.
4. Merge the approved candidate. Before any HFS write, require
   `candidate_sha == origin/main`, protected `hf`/`release` environments, private
   Space dual-layer auth, and an immutable rollback point.
5. An approved `deploy_hfs=true, publish=false` run establishes publish-ready
   live evidence. `publish=true` additionally creates the annotated tag and
   prerelease only after every gate, HFS promotion, bundle and attestation pass.

The PyInstaller and Nuitka workflows always remain builders: each produces
3 editions × 4 targets and uploads artifacts, but neither creates a Release.
Direct `HF Space CD` dispatch also remains local-only; merge/push to `main` does
not automatically deploy.

If `origin/main` advances beyond an unmerged candidate, the candidate must absorb
that change and all affected gates must rerun. If a publish attempt pushes the
annotated tag but fails before completing the Release, do not move or overwrite
the tag: stop, inspect the draft/partial state, withdraw it if necessary, and use
the next RC version rather than silently retrying against a different SHA.

## AI Workflow Policy

AI workflows keep manual `workflow_dispatch` entrypoints. Automatic triggers are
disabled by default and should only be re-enabled after confirming the target
branch, token permissions, and cost/latency expectations:

- `ai-review.yml`: automatic `pull_request` review is commented out.
- `ai-agent.yml`: automatic `issue_comment` ChatOps is commented out.
- `ai-repo-audit.yml`: manual audit only.

Manual AI runs are optional side checks. They are not completion gates for v2
implementation or release-candidate work.
