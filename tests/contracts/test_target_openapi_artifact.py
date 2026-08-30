"""Canonical target OpenAPI artifact and compatibility gate tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from souwen.delivery.api.openapi_artifact import (
    TARGET_OPENAPI_PATHS,
    build_target_openapi_document,
    canonical_openapi_bytes,
    semantic_diff_openapi,
)
from tools.gen_openapi import main


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = REPOSITORY_ROOT / "contracts/openapi/souwen-openapi-2.0.0rc6.json"


def test_checked_artifact_is_the_exact_target_only_materialization() -> None:
    document = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert ARTIFACT.read_bytes() == canonical_openapi_bytes()
    assert document == build_target_openapi_document()
    assert set(document["paths"]) == TARGET_OPENAPI_PATHS
    assert document["info"]["version"] == "2.0.0rc6"
    assert document["components"]["securitySchemes"] == {
        "UserToken": {"type": "http", "scheme": "bearer"}
    }
    assert document["paths"]["/api/v1/fetch"]["post"]["operationId"] == "fetch"
    assert document["paths"]["/api/v1/fetch"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/FetchRequest"}


def test_openapi_materialization_is_stable_and_detached_from_callers() -> None:
    first = build_target_openapi_document()
    first["paths"].clear()

    second = build_target_openapi_document()

    assert set(second["paths"]) == TARGET_OPENAPI_PATHS
    assert canonical_openapi_bytes(second) == canonical_openapi_bytes()


def test_openapi_materialization_is_identical_in_clean_interpreters(tmp_path: Path) -> None:
    script = (
        "from souwen.delivery.api.openapi_artifact import canonical_openapi_bytes; "
        "import sys; sys.stdout.buffer.write(canonical_openapi_bytes())"
    )
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
    }

    first = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=env,
    ).stdout
    second = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=env,
    ).stdout

    assert first == second == ARTIFACT.read_bytes()


def test_semantic_diff_accepts_additions_and_rejects_contract_changes() -> None:
    baseline = build_target_openapi_document()
    additive = deepcopy(baseline)
    additive["paths"]["/api/v1/new"] = {
        "get": {"operationId": "newOperation", "responses": {"200": {"description": "OK"}}}
    }
    additive["components"]["schemas"]["NewSchema"] = {"type": "object"}

    additive_report = semantic_diff_openapi(baseline, additive)

    assert additive_report == {
        "added_operations": ["GET /api/v1/new"],
        "removed_operations": [],
        "changed_operations": [],
        "added_schemas": ["NewSchema"],
        "removed_schemas": [],
        "changed_schemas": [],
        "metadata_changes": [],
        "breaking": False,
    }

    breaking = deepcopy(baseline)
    del breaking["paths"]["/api/v1/fetch"]
    breaking["paths"]["/api/v1/search"]["post"]["operationId"] = "renamedSearch"
    breaking["components"]["schemas"]["SearchRequest"]["description"] = "changed"
    breaking["components"]["headers"]["X-Request-ID"]["required"] = False
    breaking["x-souwen-api-major"] = 3
    breaking["x-souwen-rollout-mode"] = "legacy"

    breaking_report = semantic_diff_openapi(baseline, breaking)

    assert breaking_report["removed_operations"] == ["POST /api/v1/fetch"]
    assert breaking_report["changed_operations"] == ["POST /api/v1/search"]
    assert breaking_report["changed_schemas"] == ["SearchRequest"]
    assert breaking_report["metadata_changes"] == [
        "components.headers",
        "x-souwen-api-major",
        "x-souwen-rollout-mode",
    ]
    assert breaking_report["breaking"] is True


def test_semantic_diff_ignores_release_version_only() -> None:
    baseline = build_target_openapi_document("2.0.0rc5")
    candidate = build_target_openapi_document("2.0.0rc6")

    assert semantic_diff_openapi(baseline, candidate) == {
        "added_operations": [],
        "removed_operations": [],
        "changed_operations": [],
        "added_schemas": [],
        "removed_schemas": [],
        "changed_schemas": [],
        "metadata_changes": [],
        "breaking": False,
    }


def test_generator_write_check_and_machine_readable_semantic_report(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    report_path = tmp_path / "semantic.json"

    assert main(["--write", "--output", str(generated)]) == 0
    assert generated.read_bytes() == ARTIFACT.read_bytes()
    assert main(["--check", "--output", str(generated)]) == 0
    assert (
        main(
            [
                "--semantic-check",
                str(generated),
                "--json-report",
                str(report_path),
            ]
        )
        == 0
    )
    assert json.loads(report_path.read_text(encoding="utf-8"))["breaking"] is False

    generated.write_text("{}", encoding="utf-8")
    assert main(["--check", "--output", str(generated)]) == 1
