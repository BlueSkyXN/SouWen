"""Deterministic Python SDK generation from the frozen OpenAPI artifact."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from souwen.delivery.client_sdk import OPENAPI_SHA256, SDK_VERSION, SUPPORTED_API_MAJOR
from souwen.delivery.client_sdk import _generated_models as models
from souwen.delivery.client_sdk._generated_operations import OPERATIONS
from tools import gen_client_sdk


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPOSITORY_ROOT / "contracts/openapi/souwen-openapi-2.0.0rc2.json"
GENERATED_ROOT = REPOSITORY_ROOT / "src/souwen/delivery/client_sdk"


def test_generated_sdk_files_are_current_and_record_exact_artifact() -> None:
    artifact_payload = ARTIFACT.read_bytes()
    document = json.loads(artifact_payload)

    assert gen_client_sdk.main(["--check"]) == 0
    assert OPENAPI_SHA256 == hashlib.sha256(artifact_payload).hexdigest()
    assert SDK_VERSION == document["info"]["version"] == "2.0.0rc2"
    assert SUPPORTED_API_MAJOR == document["x-souwen-api-major"] == 2
    assert set(models.__all__) == set(document["components"]["schemas"])
    assert set(OPERATIONS) == {
        operation["operationId"]
        for path_item in document["paths"].values()
        for method, operation in path_item.items()
        if method in gen_client_sdk.HTTP_METHODS
    }
    assert OPERATIONS["readyz"].response_statuses == (200, 503)
    assert OPERATIONS["readinessLegacyAlias"].response_statuses == (200, 503)


def test_generator_reproduces_tracked_bindings_in_a_fresh_directory(tmp_path: Path) -> None:
    output = tmp_path / "sdk"

    assert gen_client_sdk.main(["--write", "--output", str(output)]) == 0
    assert gen_client_sdk.main(["--check", "--output", str(output)]) == 0

    for name in ("_generated_models.py", "_generated_operations.py"):
        assert (output / name).read_bytes() == (GENERATED_ROOT / name).read_bytes()


def test_generator_fails_closed_for_unapproved_operations(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["paths"]["/api/v1/legacy"] = {
        "get": {
            "operationId": "legacy",
            "security": [{"UserToken": []}],
            "responses": {
                "200": {
                    "description": "legacy",
                    "headers": {
                        name: {"$ref": f"#/components/headers/{name}"}
                        for name in (
                            "X-SouWen-API-Major",
                            "X-Request-ID",
                            "X-SouWen-Rollout-Mode",
                        )
                    },
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ProbeResponse"}
                        }
                    },
                }
            },
        }
    }
    artifact = tmp_path / "invalid.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert (
        gen_client_sdk.main(
            [
                "--write",
                "--artifact",
                str(artifact),
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "output").exists()


def test_generator_fails_closed_for_duplicate_operation_id(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(document["paths"]["/api/v1/search"]["post"])
    document["paths"] = {
        "/api/v1/unexpected": {"get": duplicate},
        **document["paths"],
    }
    artifact = tmp_path / "invalid.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert (
        gen_client_sdk.main(
            [
                "--write",
                "--artifact",
                str(artifact),
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "output").exists()


def test_generator_fails_closed_for_unsupported_schema_shape(tmp_path: Path) -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    document["components"]["schemas"]["SearchRequest"]["properties"]["query"] = {
        "oneOf": [{"type": "string"}, {"type": "integer"}]
    }
    artifact = tmp_path / "invalid.json"
    artifact.write_text(json.dumps(document), encoding="utf-8")

    assert (
        gen_client_sdk.main(
            [
                "--write",
                "--artifact",
                str(artifact),
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "output").exists()
