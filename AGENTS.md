# SouWen agent instructions

## Purpose

SouWen is a Python 3.10+ target-only information-retrieval API for AI agents:
Search, LLM Search and Fetch, a frozen OpenAPI/generated SDK surface, a FastAPI
server, and an embedded React/Vite management panel.

## Codex startup behavior

- Codex is normally launched from the repository root.
- This root `AGENTS.md` is the startup router and must stay small enough to load
  automatically.
- Subdirectory `AGENTS.md` files are navigation cards. They are not assumed to be
  in context during root-launched sessions.
- Before editing any path that has a local `AGENTS.md`, read that card first.
- If multiple nested cards exist on the path to a target file, read them from
  shallow to deep before editing.
- If a future `AGENTS.override.md` appears, stop and ask how to handle it before
  changing the ordinary `AGENTS.md` in the same directory.

## Directory map

| Path | Responsibility | Local AGENTS.md | Read when |
|---|---|---:|---|
| `src/souwen/` | Main Python package; public root is the generated SDK/client surface | yes | Any Python package change not covered by a deeper row |
| `src/souwen/common_runtime/` | Shared transport, security, resilience, observability and Provider support | no | Changing low-level HTTP/OAuth/retry/SSRF/session/cache or runtime infrastructure |
| `src/souwen/config/` | `SouWenConfig`, config template, YAML/.env/env loading and validators | yes | Changing config fields, env parsing, auth config or source credential resolution |
| `src/souwen/delivery/` | Frozen target API, generated Python SDK and Browser Worker client | no | Changing canonical HTTP contract, SDK generation/runtime or delivery adapters |
| `src/souwen/modules/` | Search, LLM Search and Fetch application services | no | Changing the three public capability workflows, selection or canonical result mapping |
| `src/souwen/platform/` | Provider SPI, spec, manifest registry and Provider manager | no | Changing Provider lifecycle, conformance, eligibility, selection or catalog semantics |
| `src/souwen/providers/` | Built-in Provider v2 packages and deterministic manifest catalog | no | Adding/removing/classifying providers or changing manifest/spec/adapter ownership |
| `src/souwen/providers/runtime_clients/` | Private provider transport/parsing clients and local catalog runtime | no | Changing provider-specific HTTP, parsing, OAuth, scraping, persistence or normalization |
| `src/souwen/server/` | FastAPI app, auth, middleware, limiter, routes, WARP and embedded panel boundary | yes | Changing API app lifecycle, auth, middleware, server wiring, WARP or panel artifact behavior |
| `src/souwen/server/routes/` | Host-only `/whoami` and read-only Admin route wiring | yes | Changing host route auth, response wrapping or route registration |
| `src/souwen/server/routes/admin/` | Read-only Admin config/doctor/ping endpoints | yes | Changing admin projection, redaction, Provider health or admin permissions |
| `src/souwen/server/schemas/` | Host-only Admin/common response schemas | yes | Changing Admin fields, validation constraints or error response shape |
| `src/souwen/worker/` | Private authenticated Browser Worker runtime | no | Changing loopback worker lifecycle, SSRF enforcement or browser execution |
| `panel/` | Single Calm Precision React/Vite/TypeScript panel, npm scripts and embedded artifact build | yes | Changing Panel UI, frontend build config, dependencies, Vite, package scripts or artifact behavior |
| `panel/src/core/` | Generated TypeScript SDK, auth/admin services, stores, shared types, styles and tests | yes | Changing SDK output, API/admin services, auth store, shared types, URL safety or tests |
| `tests/` | Deterministic pytest suite and fixtures | yes | Adding/changing Python tests, fixtures, isolation behavior or test package layout |
| `docs/` | User/contributor docs, ADRs, API docs and generated source catalog docs | yes | Changing docs, generated docs, API docs or docs tied to behavior changes |
| `scripts/` | Functional checks, smoke/profile helpers and runtime shell scripts | yes | Changing non-pytest functional checks, reports, outcomes or smoke script behavior |
| `scripts/ci/` | Deterministic CI profile runner and helper gates | yes | Changing `run_profile.py`, profile semantics or CI helper checks |
| `tools/` | OpenAPI/SDK/docs generators and validators | yes | Changing generated contracts, clients or Provider catalog documentation |
| `examples/` | Runnable public examples | yes | Changing examples or public API usage samples |
| `cloud/` | Hugging Face Space and ModelScope deployment wrappers | yes | Changing cloud Dockerfiles, entrypoints, platform README or deployment assumptions |
| `.github/` | GitHub Actions, prompts, labeler and dependency automation | yes | Changing workflow jobs, permissions, CI gates, deploy/release triggers or prompts |
| `pyproject.toml`, `hatch_build.py` | Package metadata and wheel artifact hook | no | Changing packaging metadata, optional extras or wheel artifact behavior |
| `Dockerfile`, `docker-compose.yml`, `entrypoint.sh` | Root container runtime, WARP startup and compose wiring | no | Changing Docker build/runtime, exposed ports, WARP startup, healthcheck or root image behavior |
| `souwen.example.yaml`, `.env.example` | Tracked example config and environment surface | no | Adding/removing config fields, auth defaults, WARP settings or source credential examples |
| `local/` | Gitignored local planning/review notes | no | Usually do not edit unless the user explicitly asks |
| `.codex/`, `.claude/` | Local tool/worktree metadata, not tracked project source | no | Do not edit as part of repository changes unless explicitly requested |
| `dist/`, `panel/dist/`, `src/souwen/server/panel.html` | Generated build artifacts | no | Do not hand edit; regenerate from source commands only |
| `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` | Dependency/cache output | no | Do not edit, stage or add rules here |

## On-demand cat protocol

Before editing files under a directory that has a local `AGENTS.md`, read that
file first with `cat <path>/AGENTS.md`. For nested paths, read all cards on the
path from shallow to deep. Example: before editing
`src/souwen/server/routes/admin/doctor.py`, read `src/souwen/AGENTS.md`,
`src/souwen/server/AGENTS.md`, `src/souwen/server/routes/AGENTS.md`, and
`src/souwen/server/routes/admin/AGENTS.md`.

Do not assume a card has been read because it exists in the repository. The
directory map above is the router for root-launched sessions.

## Confirmed commands

Install commands may need network access unless dependencies are already cached.

| Command | Purpose | Scope | Sandbox notes |
|---|---|---|---|
| `pip install -e ".[dev]"` | Python dev install | repo | May need network |
| `pip install -e ".[dev,server,tls,web,robots,scraper]"` | Server runtime dev install | repo | May need network |
| `pip install -e ".[dev,server,tls,web,robots,scraper,newspaper,readability]"` | Provider runtime dev install without mutually exclusive browser stacks | repo | May need network and optional native deps |
| `cd panel && npm ci` | Frontend dependency install | `panel/` | May need network; use npm only |
| `ruff check src tests scripts` | Python lint | repo | Deterministic after deps installed |
| `ruff format --check src tests scripts` | Python format check | repo | Deterministic after deps installed |
| `pytest tests/ -v --tb=short` | Full deterministic Python tests | repo | No real internet, browser runtime, production secrets or HOME config |
| `pytest tests/path/test_file.py -v --tb=short` | Targeted pytest | repo | Prefer for focused changes |
| `python tools/gen_docs.py --check` | Verify generated source catalog docs | repo | Deterministic |
| `python tools/gen_docs.py --write` | Regenerate Provider docs and managed README/architecture sections | repo | Writes generated docs |
| `python scripts/ci/check_no_legacy_terms.py` | Source catalog legacy term gate | repo | Deterministic |
| `python scripts/ci/run_profile.py --list-profiles` | List CI profiles | repo | Deterministic |
| `python scripts/ci/run_profile.py --profile server-contract` | Server target-contract smoke | repo | Requires the explicit Server runtime closure |
| `python scripts/ci/run_profile.py --profile sdk-contract` | Frozen OpenAPI plus generated Python/TypeScript SDK contract | repo | Deterministic after dev dependencies are installed |
| `python scripts/ci/run_profile.py --profile provider-runtime` | Internal optional-provider runtime smoke | repo | Requires explicit provider extras; not a public product profile |
| `cd panel && npm test` | Vitest suite | `panel/` | Deterministic after `npm ci` |
| `cd panel && npm run build` | TypeScript build plus Vite build | `panel/` | Deterministic after `npm ci` |
| `cd panel && npm run build:local && npm run check:artifact` | Rebuild embedded panel artifact | `panel/` | Writes `src/souwen/server/panel.html` |
| `docker build -t souwen .` | Docker image build | repo | Needs Docker daemon and usually network |
| `docker compose up -d` | Local compose runtime | repo | Needs Docker daemon and runtime cleanup |

There is no standalone frontend typecheck script; `npm run build` runs
`tsc -b && vite build`. There is no database migration framework in this repo.

## Global rules

- Default communication with the user is Chinese; keep code, paths, commands and
  API names in English.
- Check `git status --short` before edits. Preserve unrelated user changes.
- Use npm for `panel/`; do not add pnpm/yarn/bun lockfiles.
- Python source targets Python 3.10+ and Ruff line length 100.
- Provider `manifest.py` files, loaded through `providers.catalog` and
  `ManifestRegistry`, are the source of truth. Do not create parallel Provider
  lists in Server, Panel, docs or examples.
- Prefer existing Common Runtime transport/security helpers, Provider SPI/spec,
  `ProviderManager`, canonical delivery schemas and private runtime clients over
  ad hoc infrastructure.
- Keep ordinary pytest deterministic: no real internet, browser runtime,
  production secret, private account or local HOME config dependency.
- Put real package/browser/external smoke in functional scripts or GitHub
  Actions jobs, not ordinary pytest.
- Treat root packaging and runtime files (`pyproject.toml`,
  `hatch_build.py`, `Dockerfile`, `entrypoint.sh`, `souwen.example.yaml`) as
  cross-surface changes; check affected docs, workflows and tests before edits.
- For generated output, modify the source/generator and rerun the documented
  generation command.

## Do not

- Do not hand edit generated/cache/dependency output: `dist/`, `panel/dist/`,
  `src/souwen/server/panel.html`, `node_modules/`, `__pycache__/`,
  `.pytest_cache/`, `.ruff_cache/`.
- Do not reintroduce retired auth fields `api_password` or `visitor_password`.
- Do not default-open admin APIs; no-password admin access requires explicit
  `SOUWEN_ADMIN_OPEN=1`.
- Do not bypass fetch SSRF protections, route auth dependencies, rate limits,
  manifest/spec validation or Provider lifecycle management.
- Do not print or commit real secrets, tokens, cookies, passwords or private
  service URLs.
- Do not run destructive git commands or include unrelated worktree changes in
  commits.

## Validation

Choose the narrowest validation that covers the changed surface.

1. Read every relevant local `AGENTS.md` before editing.
2. For Python behavior changes, run targeted pytest plus `ruff check` when
   practical.
3. For Provider changes, run the affected Provider v2 tests,
   `pytest tests/test_manifest_registry_v2.py tests/test_provider_manager_v2.py -v --tb=short`,
   `python tools/gen_docs.py --check`, and
   `python scripts/ci/check_no_legacy_terms.py`.
4. For server/API changes, run affected `tests/test_server` tests and consider
   `python scripts/ci/run_profile.py --profile server-contract`.
5. For package or wheel surface changes, run `pytest tests/test_import_surface.py -q`
   and consider the relevant `scripts/ci/run_profile.py` profile.
6. For panel changes, run `cd panel && npm test` and/or `cd panel && npm run build`.
7. For embedded panel artifact changes, regenerate through
   `cd panel && npm run build:local`, never by hand.
8. If validation cannot run because dependencies, network, Docker, browser
   runtime or secrets are unavailable, state that clearly in the final response.

## Done means

- Only the requested scope was changed; unrelated worktree files were preserved.
- Generated artifacts were regenerated only through their source command.
- Relevant targeted validation was run, or the reason it was not run is stated.
- Final notes include changed files, validation, residual risk and any commands
  requiring network, Docker, secrets or manual follow-up.
