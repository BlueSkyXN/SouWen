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

## Stacked PR Delivery

Use stacked bases only for independently reviewable migration slices. Keep each
layer Draft until every dependency below it has merged. When a layer becomes the
bottom of the remaining stack:

1. Merge its dependency with a **merge commit**. Do not squash or rebase-merge
   unless every downstream branch will be explicitly restacked onto the new
   `main`; otherwise Git ancestry no longer proves that the downstream PR contains
   only its own slice.
2. Retarget the next Draft PR to `main` and verify that its head SHA and isolated
   diff are unchanged.
3. After maintainer approval, mark that PR ready for review. Main-targeted CI,
   V2 CI, HF Space local gates, and path-applicable External Smoke gates include
   the `ready_for_review` activity so this transition creates fresh PR-context
   evidence. Retargeting alone is not gate evidence.
4. Require applicable checks and review on the exact head before selecting the
   merge-commit method. Read back the resulting `main` merge commit before
   continuing with the next layer.

Workflow-dispatch evidence collected while a PR targets another stack branch is
useful pre-review evidence, but it does not replace the fresh main-targeted PR
checks above.

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

Since 2026-07-26 both workflows run in two lanes (owner-approved CI slimming):

- fast lane (ordinary PRs and `main` pushes): `CI` runs architecture, lint,
  docs-check, a single pytest combo (Python 3.13 on `ubuntu-24.04`), and
  panel-build; `V2 CI` runs bootstrap plus Provider v2 conformance.
- full lane (release `workflow_call`, manual `workflow_dispatch`, and `v*`
  tag pushes): the complete matrix and every gate below. Release evidence and
  tag acceptance are unaffected by the fast lane.

`V2 CI` must cover:

- bootstrap/import/wheel surface gate: registry/docs tests, generated docs
  freshness, removed v1 import-surface leak check, and required v2 module check.
- full pytest matrix: Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu, plus Python
  3.11 on macOS and Windows.
- Provider v2 conformance: deterministic SPI, manifest registry, Provider
  Manager, OpenAlex, builtin Fetch, UniAPI, ERIC, and PatentsView tests without network,
  browser runtime, or secrets.
- `server-contract`: local target API surface and Server prerequisite checks through
  `scripts/ci/run_profile.py`.
- `sdk-contract`: target OpenAPI, DTO and API-major prerequisite checks; this is
  not a claim that a generated SDK is complete or published.
- `provider-runtime`: internal optional-provider import, doctor and fetch-handler
  surface, including feature-matrix declarations. The mutually exclusive
  `crawl4ai` / `scrapling` browser runtime variants stay in dedicated functional gates.
- These checks install their required leaf extras explicitly. They do not create a
  product tier or package matrix.
- panel build: TypeScript check, Vitest, single-file panel build, and
  `src/souwen/server/panel.html` artifact validation.

External smoke, HF Space local preflight, the RC2 Server bundle builder, and
secret-backed checks keep their dedicated reusable/manual/schedule entrypoints.
They should not be folded into every ordinary PR. Remote HFS promotion and
GitHub publication are coordinated only by `release-candidate.yml`.

`build-pyinstaller-server.yml` builds the RC2 release inventory: exactly four
target-native PyInstaller Server bundles. The old legacy PyInstaller and Nuitka
workflows remain temporary rollback residue until the Phase 8 audit;
the central release does not call them or include their artifacts.

## Central release-candidate flow

`.github/workflows/release-candidate.yml` is the only release orchestrator. Run
it from the current `main` workflow revision with an exact 40-character
`candidate_sha`, matching prerelease version, and explicit `evidence_profile`.

1. Commit and push the candidate branch, open one integration PR to `main`, and
   require `CI / aggregate` plus `V2 CI / v2 release readiness summary` remotely.
2. After the central workflow exists on trusted `main`, run it with
   `evidence_profile=release`, `publish=false`, and `deploy_hfs=false`. The
   candidate may be a descendant of current `origin/main`; this run has no
   external release/deploy write. It generates the immutable OpenAPI artifact,
   exactly four Server bundles and their target-native smoke evidence.
3. Accept **RC-ready** only when all 15 always-required gates pass on the exact
   candidate and the evidence bundle inventory/checksums agree.
4. Merge the approved candidate. Before any HFS write, require
   `candidate_sha == origin/main`, protected `hf`/`release` environments, private
   Space dual-layer auth, and an immutable rollback point.
5. For a lightweight runtime-only acceptance, use `evidence_profile=deployment`,
   `deploy_hfs=true`, and `publish=false`. This skips the `server-bundles` release
   job but retains non-binary gates, the single HFS-local PyInstaller smoke,
   promotion, rollback and live readback. Its `deployment-evidence-*` artifact is
   not RC-ready or publish-ready evidence.
6. An approved `evidence_profile=release`, `deploy_hfs=true`, `publish=false` run
   establishes publish-ready live evidence. `publish=true` additionally creates
   the annotated tag and prerelease only after every gate, HFS promotion, bundle
   and attestation pass.

The active `build-pyinstaller-server.yml` workflow only builds and uploads the
four Server bundles; it never creates a Release. The old CLI PyInstaller/Nuitka
workflows are not part of the RC2 central release contract. Direct `HF Space CD`
dispatch also remains local-only; merge/push to `main` does not automatically
deploy.

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
