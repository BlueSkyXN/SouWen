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

## CI/CD Policy

The existing v1 workflows remain focused on `main`. v2 uses `V2 CI` for staged
pull requests to `v2-dev` while the import surface and test contracts are being
rewritten.

Do not mechanically copy v1 deployment or external smoke workflows to `v2-dev`.
Deployment, package builds, HF Space updates, Nuitka/PyInstaller builds, and
external smoke gates must be reviewed again after the v2 public surface is
stable.

## AI Workflow Policy

During v2 migration, AI workflows keep manual `workflow_dispatch` entrypoints
but automatic triggers stay disabled:

- `ai-review.yml`: automatic `pull_request` review is commented out.
- `ai-agent.yml`: automatic `issue_comment` ChatOps is commented out.
- `ai-repo-audit.yml`: manual audit only.

Manual AI runs are optional side checks. They are not completion gates for v2
implementation PRs.
