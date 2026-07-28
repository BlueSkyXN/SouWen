# OpenAPI Contract Sources

Owner: External API contract.

Language-neutral, versioned OpenAPI source documents belong here.

`souwen-openapi-2.0.0rc3.json` is the frozen target-only HTTP contract for RC3. It is generated from
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

The generated Python bindings consume this exact byte artifact:

```bash
PYTHONPATH=src python3 tools/gen_client_sdk.py --write
PYTHONPATH=src python3 tools/gen_client_sdk.py --check
```

Generated bindings record this artifact's SHA-256, API major and version. The SDK generator rejects
unknown operations, incompatible auth/header contracts and schema shapes it cannot map safely.

The generated TypeScript Panel client consumes the same bytes:

```bash
PYTHONPATH=src python3 tools/gen_typescript_sdk.py --write
PYTHONPATH=src python3 tools/gen_typescript_sdk.py --check
```

Its generator applies the same exact schema/operation allow-list and records the same artifact
SHA-256, API major and version. Runtime conformance is covered by
`panel/src/core/sdk/index.test.ts`; generation remains dependency-light and deterministic.
