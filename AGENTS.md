# SouWen agent instructions

## Purpose

SouWen is a Python 3.10+ information-retrieval toolkit for AI agents, covering
academic papers, patents, web search/fetch/archive, a FastAPI server, MCP
integration, plugin loading, and an embedded React/Vite management panel.

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
| `src/souwen/` | Main Python package, public API, models, plugin loading, client/server boundaries | yes | Any Python package change not covered by a deeper row |
| `src/souwen/core/` | Shared HTTP, OAuth, retry, parsing, scraper base, rate limit and concurrency layer | yes | Changing low-level client behavior, retry/fingerprint/session/cache, scraper base or exceptions |
| `src/souwen/config/` | `SouWenConfig`, config template, YAML/.env/env loading and validators | yes | Changing config fields, env parsing, auth config or source credential resolution |
| `src/souwen/registry/` | SourceAdapter, Source Catalog, registry loader, views and capability metadata | yes | Changing catalog shape, source defaults, capabilities, adapter validation or registry views |
| `src/souwen/registry/sources/` | Built-in source declarations and `MethodSpec` mappings | yes | Adding/removing/classifying sources or changing credentials/risk/default metadata |
| `src/souwen/paper/` | Paper provider clients and paper result normalization | yes | Changing paper providers, paper parsing, credentials or paper tests |
| `src/souwen/patent/` | Patent provider clients, OAuth credentials and patent result normalization | yes | Changing patent providers, credential handling, scraping behavior or patent tests |
| `src/souwen/web/` | Web/search/fetch/archive/social/video clients and fetch aggregation | yes | Changing web providers, fetch providers, SSRF checks, scraping behavior or routing |
| `src/souwen/web/bilibili/` | Bilibili-specific client, WBI signing, models and errors | yes | Changing Bilibili request signing, cookie behavior, upstream error mapping or models |
| `src/souwen/llm/` | LLM summarize/fetch-summarize APIs, provider adapters, prompts and models | yes | Changing LLM protocols, prompts, summary response shape, usage metadata or provider adapters |
| `src/souwen/server/` | FastAPI app, auth, middleware, limiter, routes, WARP and embedded panel boundary | yes | Changing API app lifecycle, auth, middleware, server wiring, WARP or panel artifact behavior |
| `src/souwen/server/routes/` | Public REST route handlers | yes | Changing non-admin API route behavior, auth dependency use, route timeouts or response wrapping |
| `src/souwen/server/routes/admin/` | Admin-only config/plugin/proxy/WARP/source management endpoints | yes | Changing admin routes, state mutation, secret handling or admin permissions |
| `src/souwen/server/schemas/` | FastAPI request/response schemas and OpenAPI contract | yes | Changing API fields, validation constraints, aliases or error response shape |
| `src/souwen/cli/` | Typer CLI command surface | yes | Changing CLI commands, flags, JSON output, help text or exit behavior |
| `src/souwen/integrations/` | External protocol integrations, mainly MCP | yes | Changing integration entry points, optional dependency behavior or tool wiring |
| `src/souwen/integrations/mcp/` | MCP stdio/server plus Streamable HTTP/SSE transport | yes | Changing MCP server lifecycle, transports or tools |
| `panel/` | React/Vite/TypeScript panel, npm scripts and embedded artifact build | yes | Changing frontend build config, dependencies, Vite, package scripts or panel artifact behavior |
| `panel/src/core/` | Frontend shared services, stores, hooks, types, i18n, tests and skin registry | yes | Changing API services, auth store, shared hooks/types, i18n or cross-skin behavior |
| `panel/src/skins/` | Skin modules, layouts, pages, routes, styles and skin config | yes | Changing skin UI, adding skins, routing, skin exports or CSS isolation |
| `tests/` | Deterministic pytest suite and fixtures | yes | Adding/changing Python tests, fixtures, isolation behavior or test package layout |
| `tests/registry/` | Registry/source catalog invariants | yes | Changing registry tests, catalog tests or source metadata validation |
| `docs/` | User/contributor docs, ADRs, API docs and generated source catalog docs | yes | Changing docs, generated docs, API docs or docs tied to behavior changes |
| `scripts/` | Functional checks, smoke/profile helpers and runtime shell scripts | yes | Changing non-pytest functional checks, reports, outcomes or smoke script behavior |
| `scripts/ci/` | Deterministic CI profile runner and helper gates | yes | Changing `run_profile.py`, profile semantics or CI helper checks |
| `tools/` | Repository maintenance generators and validators | yes | Changing docs generation, source id generation or plugin manifest validation |
| `examples/` | Runnable public examples and example plugin entry points | yes | Changing examples or public API usage samples |
| `examples/minimal-plugin/` | Minimal external plugin package and contract tests | yes | Changing plugin entry point, adapter, handler or plugin tests |
| `cloud/` | Hugging Face Space and ModelScope deployment wrappers | yes | Changing cloud Dockerfiles, entrypoints, platform README or deployment assumptions |
| `.github/` | GitHub Actions, prompts, labeler and dependency automation | yes | Changing workflow jobs, permissions, CI gates, deploy/release triggers or prompts |
| `cli.py`, `pyproject.toml`, `hatch_build.py` | Root CLI shim, package metadata and wheel artifact hook | no | Changing source-run CLI behavior, packaging metadata, optional extras or wheel artifact behavior |
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
`src/souwen/registry/sources/paper.py`, read `src/souwen/AGENTS.md`,
`src/souwen/registry/AGENTS.md`, and `src/souwen/registry/sources/AGENTS.md`.

Do not assume a card has been read because it exists in the repository. The
directory map above is the router for root-launched sessions.

## Confirmed commands

Install commands may need network access unless dependencies are already cached.

| Command | Purpose | Scope | Sandbox notes |
|---|---|---|---|
| `pip install -e ".[dev]"` | Python dev install | repo | May need network |
| `pip install -e ".[dev,server]"` | Python server dev install | repo | May need network |
| `pip install -e ".[dev,server,tls,web,scraper,newspaper,readability,pdf,mcp]"` | Broad CI-like runtime install | repo | May need network and optional native deps |
| `cd panel && npm ci` | Frontend dependency install | `panel/` | May need network; use npm only |
| `ruff check src tests scripts` | Python lint | repo | Deterministic after deps installed |
| `ruff format --check src tests scripts` | Python format check | repo | Deterministic after deps installed |
| `pytest tests/ -v --tb=short` | Full deterministic Python tests | repo | No real internet, browser runtime, production secrets or HOME config |
| `pytest tests/path/test_file.py -v --tb=short` | Targeted pytest | repo | Prefer for focused changes |
| `python tools/gen_docs.py --check` | Verify generated source catalog docs | repo | Deterministic |
| `python tools/gen_docs.py -o docs/data-sources.md` | Regenerate source catalog docs | repo | Writes generated docs |
| `python scripts/ci/check_no_legacy_terms.py` | Source catalog legacy term gate | repo | Deterministic |
| `python scripts/ci/run_profile.py --list-profiles` | List CI profiles | repo | Deterministic |
| `python scripts/ci/run_profile.py --profile minimal` | Minimal CLI/profile smoke | repo | Deterministic after deps installed |
| `python scripts/ci/run_profile.py --profile server --profile minimal` | Server plus minimal profile | repo | Requires server extras installed |
| `python scripts/ci/run_profile.py --profile full` | Full import-surface runtime profile | repo | Requires broad runtime extras installed |
| `python scripts/ci/run_profile.py --profile plugin` | Plugin contract/profile smoke | repo | Requires example plugin installed |
| `cd panel && npm test` | Vitest suite | `panel/` | Deterministic after `npm ci` |
| `cd panel && npm run build` | TypeScript build plus Vite build | `panel/` | Deterministic after `npm ci` |
| `cd panel && npm run build:local && npm run check:artifact` | Rebuild embedded panel artifact | `panel/` | Writes `src/souwen/server/panel.html` |
| `python tools/validate_plugin_manifest.py examples/minimal-plugin/souwen-plugin.json` | Validate example plugin manifest | repo | Deterministic |
| `pip install -e examples/minimal-plugin` | Install minimal example plugin | repo | May need local install state |
| `python scripts/plugin_functional_check.py --mode fixture --require-installed` | Real plugin entry point smoke | repo | Requires example plugin installed |
| `docker build -t souwen .` | Docker image build | repo | Needs Docker daemon and usually network |
| `docker compose up -d` | Local compose runtime | repo | Needs Docker daemon and runtime cleanup |
| `python scripts/scrapling_functional_check.py ...` | Live Scrapling functional check | repo | May need browser/runtime/network |
| `python scripts/crawl4ai_functional_check.py ...` | Live Crawl4AI functional check | repo | May need browser/runtime/network |

There is no standalone frontend typecheck script; `npm run build` runs
`tsc -b && vite build`. There is no database migration framework in this repo.

## Global rules

- Default communication with the user is Chinese; keep code, paths, commands and
  API names in English.
- Check `git status --short` before edits. Preserve unrelated user changes.
- Use npm for `panel/`; do not add pnpm/yarn/bun lockfiles.
- Python source targets Python 3.10+ and Ruff line length 100.
- Registry is the source of truth for data sources. Do not create parallel
  source lists in CLI, Server, Panel, docs or examples.
- Prefer existing `SouWenHttpClient`, `OAuthClient`, `BaseScraper`, registry
  adapters, schemas and helper APIs over ad hoc infrastructure.
- Keep ordinary pytest deterministic: no real internet, browser runtime,
  production secret, private account or local HOME config dependency.
- Put real package/browser/external smoke in functional scripts or GitHub
  Actions jobs, not ordinary pytest.
- Treat root packaging and runtime files (`pyproject.toml`, `cli.py`,
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
- Do not bypass fetch SSRF protections, route auth dependencies, rate limits or
  registry validation.
- Do not print or commit real secrets, tokens, cookies, passwords or private
  service URLs.
- Do not run destructive git commands or include unrelated worktree changes in
  commits.

## Validation

Choose the narrowest validation that covers the changed surface.

1. Read every relevant local `AGENTS.md` before editing.
2. For Python behavior changes, run targeted pytest plus `ruff check` when
   practical.
3. For registry/source changes, run `pytest tests/registry -v --tb=short`,
   `python tools/gen_docs.py --check`, and
   `python scripts/ci/check_no_legacy_terms.py`.
4. For server/API changes, run affected `tests/test_server` tests and consider
   `python scripts/ci/run_profile.py --profile server --profile minimal`.
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
