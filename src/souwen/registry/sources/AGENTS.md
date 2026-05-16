# src/souwen/registry/sources navigation card

This directory declares built-in source adapters.
Read `_helpers.py`, the target segment file, the real client module, and `docs/adding-a-source.md` first.
Read this card when adding, removing, classifying or changing source metadata.

## Key files

- `paper.py`, `patent.py`, `web_general.py`, `web_professional.py`, `fetch.py`.
- Domain segments such as `social.py`, `video.py`, `developer.py`.

## Local invariants

- New built-in source usually means client implementation plus one `_reg(SourceAdapter(...))`.
- `client_loader` must use `lazy("module:Class")`.
- `MethodSpec.param_map` targets must exist in the client method signature.
- Required credentials need complete `credential_fields`.

## Do not

- Do not mirror source facts into CLI, Server, Panel or docs.
- Do not use `extra_domains` except the currently allowed `{"fetch"}`.

## Validation

- `pytest tests/registry/test_consistency.py -v`
- `python tools/gen_docs.py --check`
