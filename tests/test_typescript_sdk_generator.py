"""Deterministic TypeScript SDK generation from the frozen target OpenAPI artifact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import gen_typescript_sdk


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPOSITORY_ROOT / "contracts/openapi/souwen-openapi-2.0.0rc3.json"
GENERATED = REPOSITORY_ROOT / "panel/src/core/sdk/index.ts"


def test_generated_typescript_sdk_is_current_and_records_exact_artifact() -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    source = GENERATED.read_text(encoding="utf-8")

    assert gen_typescript_sdk.main(["--check"]) == 0
    assert f"export const SDK_VERSION = {document['info']['version']!r} as const" in source
    assert f"export const SUPPORTED_API_MAJOR = {document['x-souwen-api-major']} as const" in source
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() in source
    assert set(document["components"]["schemas"]) == gen_typescript_sdk.EXPECTED_SCHEMAS
    for schema_name in gen_typescript_sdk.EXPECTED_SCHEMAS:
        assert (
            f"export interface {schema_name} {{" in source
            or f"export type {schema_name} = " in source
        )
    assert "This is a Panel/Vite client" in source
    assert "import.meta.env.VITE_ALLOWED_API_HOSTS" in source
    for operation_id in gen_typescript_sdk.EXPECTED_OPERATIONS:
        assert f"  {operation_id}: {{" in source


def test_write_then_check_is_reproducible_and_check_does_not_write(tmp_path: Path) -> None:
    output = tmp_path / "sdk" / "index.ts"

    assert gen_typescript_sdk.main(["--write", "--output", str(output)]) == 0
    before = output.read_bytes()
    before_mtime = output.stat().st_mtime_ns

    assert gen_typescript_sdk.main(["--check", "--output", str(output)]) == 0
    assert output.read_bytes() == before
    assert output.stat().st_mtime_ns == before_mtime


def test_unknown_schema_fails_closed(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["components"]["schemas"]["UnexpectedSchema"] = {"type": "object"}
    artifact = tmp_path / "unexpected-schema.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert gen_typescript_sdk.main(["--check", "--artifact", str(artifact)]) == 2


def test_duplicate_operation_id_fails_closed(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["paths"]["/healthz"]["get"]["operationId"] = "search"
    artifact = tmp_path / "duplicate-operation.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert gen_typescript_sdk.main(["--check", "--artifact", str(artifact)]) == 2


def test_unknown_operation_fails_closed(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["paths"]["/unexpected"] = {
        "get": document["paths"]["/healthz"]["get"] | {"operationId": "unexpected"}
    }
    artifact = tmp_path / "unexpected-operation.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert gen_typescript_sdk.main(["--check", "--artifact", str(artifact)]) == 2


def test_duplicate_schema_key_in_raw_json_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "duplicate-schema.json"
    artifact.write_text(
        '{"components":{"schemas":{"SearchRequest":{},"SearchRequest":{}}}}',
        encoding="utf-8",
    )

    with pytest.raises(gen_typescript_sdk.GenerationError, match="duplicate JSON key"):
        gen_typescript_sdk._load_document(artifact)


def test_inline_object_with_properties_fails_closed(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["components"]["schemas"]["ValidationError"]["properties"]["ctx"] = {
        "type": "object",
        "properties": {"unexpected": {"type": "string"}},
    }
    artifact = tmp_path / "inline-object.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert gen_typescript_sdk.main(["--check", "--artifact", str(artifact)]) == 2


def test_malformed_anyof_branch_fails_closed(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["components"]["schemas"]["ClientRequestContext"]["properties"]["request_id"][
        "anyOf"
    ] = [{"type": "string"}, "not-a-schema"]
    artifact = tmp_path / "malformed-anyof.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert gen_typescript_sdk.main(["--check", "--artifact", str(artifact)]) == 2
