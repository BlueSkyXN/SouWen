# SouWen agent instructions

## Purpose

SouWen is a Python 3.10+ free search & fetch tool for AI agents: exactly two
actions (`search`, `fetch`), MCP (stdio + `/mcp`) and a flat HTTP API as entries,
an egress ladder (direct → impersonate → proxy → browser) so zero-key sources
actually work, and a weekly authoritative census that deletes sources it cannot
verify.

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
- The five planning documents in `local/20261111-项目瘦身/` (gitignored) are the
  authority for the 3.x redefinition; where older docs conflict, they win.

## Directory map

| Path | Responsibility | Local AGENTS.md | Read when |
|---|---|---:|---|
| `src/souwen/agent.py` | Facade: `search` / `fetch` / `sources` shared by every entry | no | Changing the agent-facing result shapes |
| `src/souwen/cli.py` | `souwen mcp \| serve \| doctor` (incl. `--live`) | no | Changing CLI behavior |
| `src/souwen/modules/` | Search orchestration/fallback/projection; fetch reader chain | no | Changing search or fetch orchestration |
| `src/souwen/common_runtime/` | Transport, egress ladder, pinning proxy, SSRF, rate limiting | no | Changing transport/security/resilience infrastructure |
| `src/souwen/config/` | `SouWenConfig`, template, loading, validators | yes | Changing config fields or auth config |
| `src/souwen/providers/` | One package per source (`register.py` + manifest/spec/adapter) + private runtime clients | no | Adding/removing sources or changing adapters |
| `src/souwen/platform/` | Provider SPI, spec, manifest registry, manager | no | Changing provider lifecycle or catalog semantics |
| `src/souwen/server/` | FastAPI app, auth, limiter, MCP server, doctor, v2 runtime wiring | yes | Changing API surface, auth, or runtime wiring |
| `tests/` | Deterministic pytest suite | yes | Adding/changing tests |
| `scripts/census.py`, `scripts/census/` | Authoritative census client + frozen queries | yes | Changing census modes or frozen inputs |
| `tools/` | Docs generators (`gen_docs.py`, `gen_sources_doc.py`) | yes | Changing generated docs |
| `docs/` | `architecture.md`, `data-sources.md`, generated `sources.md` | yes | Changing docs |
| `.github/` | `ci.yml`, `census.yml`, `image.yml` | yes | Changing CI or the census |
| `Dockerfile`, `entrypoint.sh` | Runtime image with WARP + Chromium | no | Changing image/runtime |
| `pyproject.toml` | Metadata, extras (`server`, `mcp`, `browser`, ...), console script | no | Changing packaging or dependencies |
| `local/` | Gitignored planning/review notes (P0–P4 documents live here) | no | Never commit; read for context |
| `dist/`, `__pycache__/`, caches | Generated output | no | Do not edit |

## On-demand cat protocol

Before editing files under a directory that has a local `AGENTS.md`, read that
file first (shallow to deep for nested paths). Do not assume a card has been
read because it exists in the repository.

## Confirmed commands

| Command | Purpose | Sandbox notes |
|---|---|---|
| `ruff check src tests scripts tools` | Python lint | Deterministic |
| `ruff format --check src tests scripts tools` | Format check | Deterministic |
| `python3 -m pytest tests/ -q` | Full deterministic suite | No real internet, secrets, or HOME config |
| `python3 tools/gen_docs.py --check` / `--write` | Managed docs regions | Writes on `--write` |
| `python3 tools/gen_sources_doc.py --census <sources.json> --write docs/sources.md` | Regenerate the source census doc | Input: downloaded census artifact |
| `python3 scripts/ci/run_profile.py --list-profiles` | List CI smoke profiles | Deterministic |
| `pip install -e ".[dev,server,tls,web,robots,scraper]"` | Profile runtime dev install | Before `--profile server-contract` |
| `python3 scripts/ci/run_profile.py --profile server-contract` | Server target-contract smoke | Needs the install above |
| `python3 scripts/ci/check_no_legacy_terms.py` | Legacy-term gate | Deterministic |
| `python3 scripts/ci/check_architecture_dependencies.py` | Layering gate | Deterministic |
| `python3 -m souwen.cli doctor --live --level all` | In-process per-egress census | Network |
| push `agent-first` | Triggers `census.yml` | Authoritative environment |

## Global rules

- Default communication with the user is Chinese; keep code, paths, commands and
  API names in English.
- Check `git status --short` before edits. Preserve unrelated user changes.
- Each source package owns a `register.py` (MANIFEST / SPEC / PROVIDER_TYPE /
  `build_provider`, optional `resolve_configuration`); `manifest.py` stays the
  identity source of truth and `server/v2_runtime.py` registers everything by
  directory discovery — adding a source must not touch code outside its package.
- Keep pytest deterministic: no real internet, browser runtime, production
  secrets, or HOME config dependency. Live checks belong to `census.py` /
  `doctor --live` / Actions.
- The SSRF validator (`common_runtime/security/fetch_target.py`) and the
  user-credential auth semantics must never be loosened.
- Browser egress must keep connection-level SSRF pinning
  (`common_runtime/provider_support/browser_pinning_proxy.py`).

## Do not

- Do not reintroduce retired surfaces: `/api/v1/*`, the frozen OpenAPI, generated
  SDKs, the React Panel, Admin/guest roles, LLM Search, `api_password`,
  `visitor_password`.
- Do not print or commit real secrets, tokens, cookies, passwords, or private
  service URLs.
- Do not run destructive git commands or include unrelated worktree changes in
  commits.

## Validation

1. Read every relevant local `AGENTS.md` before editing.
2. Run targeted pytest plus `ruff check` for Python changes.
3. For provider changes: affected provider tests, `python3 tools/gen_docs.py
   --check`, `python3 scripts/ci/check_no_legacy_terms.py`.
4. For server/API changes: affected `tests/test_agent_api_v2.py` and runtime
   tests.
5. If validation cannot run because dependencies, network, Docker, or secrets
   are unavailable, state that clearly in the final response.

## Done means

- Only the requested scope was changed; unrelated worktree files were preserved.
- Generated docs were regenerated only through their source commands.
- Relevant targeted validation was run, or the reason it was not run is stated.
- Final notes include changed files, validation, residual risk, and any commands
  requiring network, Docker, secrets, or manual follow-up.
