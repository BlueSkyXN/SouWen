# src/souwen navigation card

Type: Domain card.
This directory is the main Python package for SouWen.
Read `delivery/client_sdk/`, `platform/`, and `docs/architecture.md` before broad package changes.
Read this card when changing package-level APIs, imports, shared models or cross-layer behavior.

## Local invariants

- Public imports must stay light; do not import optional provider dependencies at package import time.
- Public root imports are generated SDK/client only; Provider facts flow through `ProviderManifest`,
  `ManifestRegistry` and `ProviderManager` rather than ad hoc source dispatch.
- Canonical public DTOs come from the frozen OpenAPI artifact and generated SDK. Models under
  `providers/runtime_clients/` are private implementation details.

## Do not

- Do not add v1 compatibility modules or dispatcher tables unless tests and docs explicitly require them.
- Do not bypass `ProviderManager` or create a second Provider catalog/selection registry.
- Do not make package import depend on server or panel extras.

## Validation

- Use the nearest deeper card for focused checks.
- Broad package changes: `pytest tests/ -v --tb=short`.
- Import-surface changes: `pytest tests/test_import_surface.py -q`.
