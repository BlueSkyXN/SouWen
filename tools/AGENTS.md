# tools navigation card

Type: Domain card.
This directory contains repository maintenance generators and validators.
Read `gen_docs.py`, `gen_source_ids.py`, and `docs/data-sources.md` first.
Read this card for generated docs or source ID tooling changes.

## Local invariants

- `gen_docs.py` derives source docs from the built-in registry.
- `--check` modes must not write files.
- Output should be UTF-8 and reproducible across local environments.

## Do not

- Do not encode hand-written source facts in generators instead of registry.
- Do not hide generated-doc drift by weakening checks.
- Do not make validators depend on network access.

## Validation

- `python tools/gen_docs.py --check`
- `pytest tests/test_gen_docs.py -v --tb=short`
