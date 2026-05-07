# ADR 0001: Public API Surface

**Status**: Accepted  
**Date**: 2026-05-07  
**Scope**: SouWen `v2-dev`

## Context

`v2-dev` is the long-lived integration line for the current SouWen architecture. The branch has already removed the old facade package, domain re-export packages, and top-level compatibility modules from the wheel surface.

The next refactor phases should not reintroduce compatibility shims for paths that were never promoted as stable public contracts.

## Decision

SouWen will keep a small public API surface:

- `souwen.search`
- `souwen.web.fetch`
- `souwen.web.wayback`
- `souwen.registry`
- `souwen.registry.meta`
- `souwen.core.http_client`
- CLI entry point `souwen`
- REST API under `/api/v1`

The following paths are not public contracts and must not be restored:

- `souwen.facade`
- `souwen.fetch`
- `souwen.source_registry`
- top-level core shims such as `souwen.http_client`
- domain re-export packages such as `souwen.social`, `souwen.video`, `souwen.knowledge`, `souwen.office`, `souwen.cn_tech`, and `souwen.developer`
- old web grouping packages such as `souwen.web.engines`, `souwen.web.api`, and `souwen.web.self_hosted`

The registry is the single source of truth for source metadata, capabilities, defaults, catalog projection, docs generation, API source listing, CLI source listing, and Panel source UI.

## Consequences

- New features must use the current registry and application API paths.
- Tests may keep negative import assertions for removed paths.
- Changelog and internal docs may mention historical paths for auditability.
- Public docs should describe the current architecture instead of migration history.
- If a removed path appears in the wheel surface, CI should fail.

## Verification

Current verification should include:

```bash
PYTHONPATH=src SOUWEN_PLUGIN_AUTOLOAD=0 pytest tests/test_import_surface.py -q
```

Future phases should add a legacy-term gate for public source and docs surfaces.
