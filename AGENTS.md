# SouWen Codex instructions

## How Codex should use these files

This root `AGENTS.md` is the startup router for Codex sessions launched from the repository root. Local `AGENTS.md` files are navigation cards, not automatically loaded global rules.

Before editing files under a directory that has a local `AGENTS.md`, read that file first. If multiple nested `AGENTS.md` files exist on the path to the target file, read them from shallow to deep before making changes.

Do not assume a child card has been read just because it exists. Use the map below to decide when to `cat` a local card.

## Repository map

| Path | Responsibility | Local AGENTS.md | Read when |
|---|---|---:|---|
| `src/souwen/` | Main Python package: public API, plugin loading, models, CLI/server/client layers | yes | Any Python package change not covered by a deeper row |
| `src/souwen/core/` | Shared platform layer: HTTP, OAuth, retry, concurrency, rate limit, parsing, scraper base | yes | Changing low-level client behavior, scraper base, retry, exceptions, session/cache, concurrency |
| `src/souwen/config/` | `SouWenConfig`, YAML/.env/env loading, validators and config defaults | yes | Changing config fields, auth config, env parsing, source credential resolution |
| `src/souwen/registry/` | SourceAdapter, Source Catalog, source views, defaults and plugin-visible registry | yes | Changing catalog shape, capabilities, defaults, adapter validation or registry views |
| `src/souwen/registry/sources/` | Built-in source declarations and MethodSpec mappings | yes | Adding/removing/classifying sources or changing credentials/risk/default source metadata |
| `src/souwen/paper/` | Paper source clients and paper result normalization | yes | Changing paper providers, paper parsing, paper credentials or paper tests |
| `src/souwen/patent/` | Patent source clients and patent result normalization | yes | Changing patent providers, OAuth credentials, patent parsing or patent tests |
| `src/souwen/web/` | Web/search/fetch/archive/social/video clients and fetch aggregation | yes | Changing web providers, fetch providers, SSRF checks, scraping behavior or provider routing |
| `src/souwen/web/bilibili/` | Bilibili-specific client, WBI signing, models and errors | yes | Changing Bilibili request signing, cookie behavior, errors or models |
| `src/souwen/llm/` | LLM summarize/fetch-summarize clients, providers, prompts and models | yes | Changing LLM protocols, prompts, summary response shape or provider adapters |
| `src/souwen/server/` | FastAPI app, auth, middleware, routes, schemas, WARP and embedded panel artifact | yes | Changing API app lifecycle, auth, middleware, server routes, schemas or WARP |
| `src/souwen/server/routes/` | Public REST route handlers | yes | Changing non-admin API route behavior, auth dependency use, route timeouts or response wrapping |
| `src/souwen/server/routes/admin/` | Admin-only config/plugin/proxy/WARP/source management endpoints | yes | Changing admin routes, state mutation, secret handling or admin permissions |
| `src/souwen/server/schemas/` | FastAPI request/response schemas and OpenAPI contract | yes | Changing API models, validation constraints, aliases or error response shape |
| `src/souwen/cli/` | Typer CLI command surface | yes | Changing CLI commands, flags, JSON output, help text or exit behavior |
| `src/souwen/integrations/` | External protocol integrations, mainly MCP | yes | Changing MCP or other integration entry points and tool wiring |
| `src/souwen/integrations/mcp/` | MCP stdio/server, Streamable HTTP/SSE and tool registrations | yes | Changing MCP server/http lifecycle, transport behavior or tools |
| `panel/` | React/Vite/TypeScript web panel, build pipeline and package scripts | yes | Changing any frontend build, dependency, Vite, package script or panel artifact behavior |
| `panel/src/core/` | Frontend shared services, stores, hooks, types, i18n and tests | yes | Changing API services, auth store, shared hooks, shared types or i18n |
| `panel/src/skins/` | Skin modules: layouts, pages, styles, skin config and routes | yes | Changing skin UI, adding a skin, skin routing, skin exports or CSS isolation |
| `tests/` | Deterministic pytest suite | yes | Adding or changing Python tests, fixtures or test isolation behavior |
| `tests/registry/` | Registry/source catalog invariants | yes | Changing tests for SourceAdapter, catalog, defaults, credentials or source validation |
| `docs/` | User/contributor docs, ADRs and generated source catalog docs | yes | Changing docs, generated docs, API docs or docs tied to behavior changes |
| `scripts/` | Functional checks, smoke/profile helpers and WARP shell scripts | yes | Changing non-pytest functional checks, reports, outcomes or smoke scripts |
| `scripts/ci/` | Deterministic CI profile runner and CI helper gates | yes | Changing `run_profile.py`, profile semantics or CI helper checks |
| `tools/` | Repository maintenance generators and validators | yes | Changing docs generation, source id generation or plugin manifest validation |
| `examples/` | Runnable examples and example plugin | yes | Changing examples or public API usage samples |
| `examples/minimal-plugin/` | Minimal external plugin package and contract tests | yes | Changing plugin entry point, example adapter, handler or plugin tests |
| `cloud/` | Hugging Face Space and ModelScope deployment wrappers | yes | Changing cloud Dockerfiles, entrypoints, platform README or deployment assumptions |
| `.github/` | GitHub Actions, prompts, labeler and dependency automation | yes | Changing workflow jobs, permissions, CI gates, deployment or release automation |
| `local/` | Local planning/review notes, gitignored | no | Usually do not edit unless the user explicitly asks |
| `dist/`, `panel/dist/`, `src/souwen/server/panel.html` | Generated build artifacts | no | Do not hand edit; regenerate from source when required |
| `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` | Dependency/cache output | no | Do not edit or add rules here |

## Confirmed commands

Install commands may need network access unless dependencies are already cached.

- Python dev install: `pip install -e ".[dev]"`
- Python server install: `pip install -e ".[dev,server]"`
- Optional full-ish runtime install used by CI: `pip install -e ".[dev,server,tls,web,scraper,newspaper,readability,pdf,mcp]"`
- Frontend install: `cd panel && npm ci`

Local deterministic checks after dependencies are installed:

- Python lint: `ruff check src tests scripts`
- Python format check: `ruff format --check src tests scripts`
- Python tests: `pytest tests/ -v --tb=short`
- Targeted pytest: `pytest tests/path/test_file.py -v --tb=short`
- Registry/docs generated-content check: `python tools/gen_docs.py --check`
- Source catalog legacy term gate: `python scripts/ci/check_no_legacy_terms.py`
- CI profile list: `python scripts/ci/run_profile.py --list-profiles`
- Minimal CLI profile: `python scripts/ci/run_profile.py --profile minimal`
- Server + minimal profile: `python scripts/ci/run_profile.py --profile server --profile minimal`
- Panel test: `cd panel && npm test`
- Panel build and typecheck: `cd panel && npm run build`
- Panel artifact build: `cd panel && npm run build:local && npm run check:artifact`
- Plugin manifest validation: `python tools/validate_plugin_manifest.py examples/minimal-plugin/souwen-plugin.json`

Code generation / generated files:

- Regenerate source docs: `python tools/gen_docs.py -o docs/data-sources.md`
- Validate generated docs without writing: `python tools/gen_docs.py --check`
- Rebuild embedded panel artifact: `cd panel && npm run build:local`

Commands that usually need network, external runtime, Docker, browsers, secrets or platform access:

- Docker image build: `docker build -t souwen .`
- Docker compose run: `docker compose up -d`
- Example scripts such as `python examples/search_papers.py` may hit external services.
- Functional checks such as `python scripts/scrapling_functional_check.py ...` and `python scripts/crawl4ai_functional_check.py ...` may need browser runtimes or live network.
- `python scripts/plugin_functional_check.py --mode fixture --require-installed` requires `pip install -e examples/minimal-plugin` first.

No database migration framework or standalone frontend typecheck script is configured. Frontend typechecking is part of `npm run build` (`tsc -b && vite build`).

## Global rules

- Default communication is Chinese; keep code, paths, commands and API names in English.
- Check `git status --short` before edits. Preserve unrelated user changes and do not include them in commits.
- Use npm for `panel/`; do not add pnpm/yarn lockfiles.
- Python source targets Python 3.10+ and Ruff line length 100.
- Registry is the source of truth for data sources. Do not create parallel source lists in CLI, Server, Panel or docs.
- Prefer existing `SouWenHttpClient`, `OAuthClient`, `BaseScraper`, registry adapters, schemas and helpers over new ad hoc infrastructure.
- Keep ordinary pytest deterministic: no real internet, browser runtime, production secret or local HOME config dependency.
- Use functional scripts and GitHub Actions jobs for real package/browser/external smoke.

## Do not

- Do not hand edit generated/cache/dependency output: `dist/`, `panel/dist/`, `src/souwen/server/panel.html`, `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`.
- Do not reintroduce retired auth fields `api_password` or `visitor_password`.
- Do not default-open admin APIs; no-password admin access requires explicit `SOUWEN_ADMIN_OPEN=1`.
- Do not bypass fetch SSRF protections or route auth dependencies.
- Do not print or commit real secrets, tokens, cookies, passwords or private service URLs.

## Done means

- The nearest relevant local `AGENTS.md` cards were read before editing.
- Changes are scoped to the requested task and do not include unrelated worktree files.
- Relevant targeted validation was run, or the reason it was not run is stated.
- Generated artifacts were regenerated only through their source command.
- Final notes include changed files, validation, residual risk and any commands that require network/secrets/manual follow-up.
