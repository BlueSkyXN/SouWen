# OpenAPI Contract Sources

Owner: External API contract.

Language-neutral, versioned OpenAPI source documents belong here.

`souwen-openapi-2.0.0rc2.json` is the frozen target-only HTTP contract for RC2. It is generated from
the schema-only target Delivery app, contains no deployment configuration or runtime provenance,
and is the source for release assets and generated SDKs.

Regenerate or verify it from the repository root:

```bash
PYTHONPATH=src python3 tools/gen_openapi.py --write
PYTHONPATH=src python3 tools/gen_openapi.py --check
```

Compare a previous artifact conservatively before accepting a contract change:

```bash
PYTHONPATH=src python3 tools/gen_openapi.py \
  --semantic-check path/to/baseline.json \
  --json-report artifacts/openapi-semantic-report.json
```

Removed or changed operations/schemas and target metadata/security changes fail the semantic check.
Additive operations and schemas are reported but do not fail it.
