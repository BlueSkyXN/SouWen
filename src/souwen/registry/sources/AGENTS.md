# src/souwen/registry/sources navigation card

Type: Domain card.
This directory declares built-in source adapters and their method mappings.
Read `_helpers.py`, the target segment file, the real client module, and `docs/adding-a-source.md` before editing.
Read this card when adding, removing, classifying or changing built-in source metadata.

## Local invariants

- New built-in sources usually require a client implementation plus one `_reg(SourceAdapter(...))`.
- `client_loader` must use lazy `"module:Class"` loading; do not import clients eagerly.
- `MethodSpec.param_map` targets must exist in the client method signature.
- Required credentials need complete `credential_fields` and matching config fields.
- `extra_domains` is exceptional; keep it limited to explicitly supported cases.

## Do not

- Do not mirror source facts into CLI, Server, Panel or docs.
- Do not mark credential-heavy or high-risk sources as defaults without tests.
- Do not add a source without deterministic registry coverage.

## Validation

- `pytest tests/registry/test_consistency.py -v --tb=short`
- `python tools/gen_docs.py --check`
- `python scripts/ci/check_no_legacy_terms.py`
