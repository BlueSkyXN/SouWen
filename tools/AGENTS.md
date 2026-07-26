# tools navigation card

Type: Domain card.
This directory contains OpenAPI, generated SDK, Provider documentation and validation tooling.
Read the target generator, the frozen OpenAPI artifact and its tests first.

## Local invariants

- `gen_docs.py` derives Provider docs from the manifest catalog.
- OpenAPI and SDK generators must remain deterministic and exact-artifact reproducible.
- `--check` modes must not write files.
- Output should be UTF-8 and reproducible across local environments.

## Do not

- Do not encode hand-written Provider facts in generators instead of manifests.
- Do not hide generated-doc drift by weakening checks.
- Do not make validators depend on network access.

## Validation

- `python tools/gen_docs.py --check`
- `python tools/gen_openapi.py --check`
- `python tools/gen_client_sdk.py --check`
- `python tools/gen_typescript_sdk.py --check`
- `pytest tests/test_gen_docs.py -v --tb=short`
