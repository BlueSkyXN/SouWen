# src/souwen navigation card

Type: Domain card.
This directory is the main Python package for SouWen.
Read `search.py`, `models.py`, `plugin.py`, `plugin_manager.py`, and `docs/architecture.md` before broad package changes.
Read this card when changing package-level APIs, imports, plugin loading, shared models or cross-layer behavior.

## Local invariants

- Public imports must stay light; do not import optional provider dependencies at package import time.
- Application entry points should flow through registry/client/core layers instead of ad hoc source dispatch.
- Plugin loading must use the existing entry point, config loader and plugin manager paths.
- Shared Pydantic models in `models.py` are API surface; route, CLI and docs changes may be required.

## Do not

- Do not add v1 compatibility modules or dispatcher tables unless tests and docs explicitly require them.
- Do not bypass `src/souwen/registry/` for source selection.
- Do not make package import depend on server, panel or MCP extras.

## Validation

- Use the nearest deeper card for focused checks.
- Broad package changes: `pytest tests/ -v --tb=short`.
- Import-surface changes: `pytest tests/test_import_surface.py -q`.
