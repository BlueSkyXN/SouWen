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
- server + minimal profile: local API surface tests and CLI smoke through
  `scripts/ci/run_profile.py`.
- full runtime profile: all source, doctor, plugin, and fetch handler import
  surface through `scripts/ci/run_profile.py`.
- plugin profile: example plugin install, plugin contract tests, and entry point
  discovery through `scripts/ci/run_profile.py`.
- panel build: TypeScript check, Vitest, single-file panel build, and
  `src/souwen/server/panel.html` artifact validation.

External smoke, HF Space deploy, PyInstaller/Nuitka release artifacts, and
secret-backed checks stay on their dedicated manual, tag, schedule, or release
entrypoints. They should not be folded into every ordinary PR.

Before cutting a release candidate tag, run this release checklist:

1. `CI` and `V2 CI` are green on the candidate head.
2. `External Smoke Gate` is run manually with `suite=release` on the candidate
   head, release branch, or tag candidate.
3. `HF Space CD` is validated through its PR/local gates; real sync, factory
   rebuild, and post-deploy smoke stay on their deployment workflow entrypoints.
4. `Build with PyInstaller` and `Build with Nuitka` are run manually for the
   selected release tier/platform matrix, or by the `v*` release tag.
5. Workflow comments, branch filters, path filters, and version references are
   reviewed so `main` automation points at the v2 public surface.

## AI Workflow Policy

AI workflows keep manual `workflow_dispatch` entrypoints. Automatic triggers are
disabled by default and should only be re-enabled after confirming the target
branch, token permissions, and cost/latency expectations:

- `ai-review.yml`: automatic `pull_request` review is commented out.
- `ai-agent.yml`: automatic `issue_comment` ChatOps is commented out.
- `ai-repo-audit.yml`: manual audit only.

Manual AI runs are optional side checks. They are not completion gates for v2
implementation or release-candidate work.
