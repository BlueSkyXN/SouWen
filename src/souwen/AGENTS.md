# src/souwen navigation card

This is the main Python package for SouWen.
Read `docs/architecture.md`, `src/souwen/search.py`, `src/souwen/models.py`, and `src/souwen/plugin.py` before broad package changes.
Read this card when changing package-level APIs, imports, plugin loading, models or cross-layer behavior.

## Key files

- `search.py`: registry-driven application search API.
- `web/fetch.py`: unified fetch application API.
- `plugin.py` / `plugin_manager.py`: plugin discovery and management.
- `models.py`: shared Pydantic result models.

## Local invariants

- Dependency direction is presentation -> application API -> registry/client/core.
- Public entry points must remain import-light; avoid optional dependency imports at package import time.
- Plugin loading must go through existing entry point/config loader paths.

## Do not

- Do not add v1 compatibility modules or dispatch tables unless tests and docs explicitly require them.
- Do not bypass `registry` for source selection.

Use root validation commands.
