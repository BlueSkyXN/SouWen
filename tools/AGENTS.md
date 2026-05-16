# tools navigation card

This directory contains repository maintenance generators and validators.
Read `gen_docs.py`, `validate_plugin_manifest.py`, `docs/data-sources.md`, and `docs/plugin-manifest.schema.json` first.
Read this card for generated docs, source id or plugin manifest tooling changes.

## Local invariants

- `gen_docs.py` derives source docs from registry and disables external plugin autoload by default.
- `--check` modes must not write files.
- Output should be UTF-8 and reproducible across local environments.

## Do not

- Do not encode hand-written source facts in generators instead of registry.

## Validation

- `python tools/gen_docs.py --check`
- `pytest tests/test_gen_docs.py tests/test_plugin_manifest_validator.py -v --tb=short`
