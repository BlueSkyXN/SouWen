# SouWen v2 Development Branching

SouWen v2 is a breaking migration. Development must happen on `v2-dev` first,
then merge back to `main` only after the v2 release surface is complete.

## Branch Roles

```text
main
  Stable v1 line. Do not use it for direct v2 refactor commits.

v2-dev
  Long-lived v2 integration line. All staged v2 pull requests target this branch.

v2/*
  Short-lived implementation branches. Each branch should live in its own worktree.
```

`v2-dev` must not be rebased after publication. If `main` receives important
changes during the v2 migration, merge `origin/main` into `v2-dev` and resolve
conflicts there.

## Worktree Flow

Create each implementation branch from the latest `origin/v2-dev`:

```bash
git fetch origin
git worktree add ../SouWen-v2-01-registry -b v2/01-registry-meta origin/v2-dev
```

Open pull requests to `v2-dev`, not `main`:

```bash
gh pr create --base v2-dev --head v2/01-registry-meta
```

After a PR merges into `v2-dev`, create the next implementation branch from the
updated `origin/v2-dev`.

## PR Order

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

The existing v1 workflows remain focused on `main`. v2 uses `V2 CI` for staged
pull requests to `v2-dev` and for release-readiness validation before promoting
v2 back to `main`.

`V2 CI` is the required pre-release gate for `v2-dev`:

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

`v2-dev` must not automatically deploy or publish production artifacts. HF Space
deploy, PyPI publish, PyInstaller/Nuitka release artifacts, and secret-backed
external smoke remain on their existing `main`, tag, release, or manual
entrypoints until v2 is promoted.

Before merging v2 back to `main`, run this release checklist:

1. `V2 CI` is green on the v2 candidate head.
2. `External Smoke Gate` is run manually with `suite=release` on the v2
   candidate, or on the mergeback PR if the workflow has already been retargeted.
3. `HF Space CD` is validated without enabling `v2-dev` production deployment:
   PR/local gates must pass on the mergeback PR; real sync, factory rebuild, and
   post-deploy smoke stay `main` only.
4. `Build with PyInstaller` and `Build with Nuitka` are run manually for the
   selected release tier/platform matrix, or by the `v*` release tag after
   mergeback.
5. `发布到 PyPI` remains release/manual only; publish only from a `v*` tag after
   tag/version consistency and package artifact checks pass.
6. Workflow comments, branch filters, path filters, and version references are
   reviewed so the restored `main` automation points at the v2 public surface.

## AI Workflow Policy

During v2 migration, AI workflows keep manual `workflow_dispatch` entrypoints
but automatic triggers stay disabled:

- `ai-review.yml`: automatic `pull_request` review is commented out.
- `ai-agent.yml`: automatic `issue_comment` ChatOps is commented out.
- `ai-repo-audit.yml`: manual audit only.

Manual AI runs are optional side checks. They are not completion gates for v2
implementation PRs.
