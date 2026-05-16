# examples/minimal-plugin navigation card

Type: Domain card.
This directory is the minimal external SouWen plugin package and contract-test fixture.
Read `README.md`, `pyproject.toml`, `souwen-plugin.json`, `souwen_example_plugin/__init__.py`, `client.py`, `handler.py`, `docs/plugin-integration-spec.md`, and `scripts/plugin_functional_check.py` first.
Read this card for plugin entry point, adapter, handler, manifest or contract test changes.

## Local invariants

- The example plugin stays minimal, offline and dependency-light.
- Entry point name, adapter name and fetch handler owner must match tests and functional checks.
- SouWen is a runtime peer dependency, not a path dependency in this package.
- Manifest fields must validate against `docs/plugin-manifest.schema.json`.

## Do not

- Do not make the minimal example a complex commercial plugin.
- Do not override built-in sources.
- Do not require live network or real credentials for plugin contract tests.

## Validation

- `pip install -e examples/minimal-plugin` (may need local install state)
- `pytest examples/minimal-plugin/tests -v --tb=short`
- `python scripts/plugin_functional_check.py --mode fixture --require-installed`
