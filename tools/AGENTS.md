# tools navigation card

Type: Domain card.
This directory contains repository maintenance generators and validators.
Read `gen_docs.py`, `gen_source_ids.py`, `validate_plugin_manifest.py`, `docs/data-sources.md`, and `docs/plugin-manifest.schema.json` first.
Read this card for generated docs, source ID tooling or plugin manifest validation changes.

## Local invariants

- `gen_docs.py` derives source docs from registry and disables external plugin autoload by default.
- `--check` modes must not write files.
- Output should be UTF-8 and reproducible across local environments.
- Plugin manifest validation must stay aligned with `docs/plugin-manifest.schema.json`.

## Do not

- Do not encode hand-written source facts in generators instead of registry.
- Do not hide generated-doc drift by weakening checks.
- Do not make validators depend on network access.

## Validation

- `python tools/gen_docs.py --check`
- `pytest tests/test_gen_docs.py tests/test_plugin_manifest_validator.py -v --tb=short`
