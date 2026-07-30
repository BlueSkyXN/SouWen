#!/usr/bin/env python3
"""Generate the dependency-light Python SDK bindings from canonical OpenAPI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = REPOSITORY_ROOT / "contracts/openapi/souwen-openapi-2.0.0rc5.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "src/souwen/delivery/client_sdk"
GENERATOR_VERSION = 1
EXPECTED_VERSION = "2.0.0rc5"
EXPECTED_API_MAJOR = 2
EXPECTED_OPERATIONS = {
    "fetch": ("POST", "/api/v1/fetch", "FetchRequest", "FetchBatch", (200,)),
    "llmSearch": (
        "POST",
        "/api/v1/llm-search",
        "LLMSearchRequest",
        "LLMSearchResult",
        (200,),
    ),
    "listProviders": ("GET", "/api/v1/providers", None, "ProviderCatalog", (200,)),
    "search": ("POST", "/api/v1/search", "SearchRequest", "SearchPage", (200,)),
    "healthAlias": ("GET", "/health", None, "ProbeResponse", (200,)),
    "healthz": ("GET", "/healthz", None, "ProbeResponse", (200,)),
    "readinessAlias": ("GET", "/readiness", None, "ProbeResponse", (200, 503)),
    "readyz": ("GET", "/readyz", None, "ProbeResponse", (200, 503)),
}
HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}


class GenerationError(ValueError):
    """The canonical artifact cannot be mapped without widening its contract."""


def _load_document(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot read canonical OpenAPI artifact {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise GenerationError("canonical OpenAPI root must be an object")
    return document, payload


def _ref_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    prefix = "#/components/schemas/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        raise GenerationError(f"operation schema must use a component ref: {schema!r}")
    return ref.removeprefix(prefix)


def _validate_document(document: dict[str, Any]) -> None:
    if document.get("info", {}).get("version") != EXPECTED_VERSION:
        raise GenerationError(f"SDK requires OpenAPI version {EXPECTED_VERSION}")
    if document.get("x-souwen-api-major") != EXPECTED_API_MAJOR:
        raise GenerationError(f"SDK requires API major {EXPECTED_API_MAJOR}")
    if document.get("x-souwen-rollout-mode") != "target":
        raise GenerationError("SDK can only be generated from target rollout OpenAPI")
    security = document.get("components", {}).get("securitySchemes", {}).get("UserToken")
    if security != {"type": "http", "scheme": "bearer"}:
        raise GenerationError("UserToken must remain an HTTP bearer security scheme")

    observed: dict[str, tuple[str, str, str | None, str, tuple[int, ...]]] = {}
    observed_signatures: set[tuple[str, str, str]] = set()
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            raise GenerationError(f"invalid path item: {path}")
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict) or not isinstance(operation.get("operationId"), str):
                raise GenerationError(f"operationId is required for {method.upper()} {path}")
            request_schema = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            responses = operation.get("responses", {})
            response_schema = (
                responses.get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            operation_id = operation["operationId"]
            if operation_id in observed:
                raise GenerationError(f"duplicate operationId: {operation_id}")
            observed_signatures.add((method.upper(), path, operation_id))
            response_model = _ref_name(response_schema)
            model_statuses: list[int] = []
            for status, response in responses.items():
                try:
                    status_code = int(status)
                except (TypeError, ValueError) as exc:
                    raise GenerationError(
                        f"operation {operation_id} uses non-numeric response status {status!r}"
                    ) from exc
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                model = _ref_name(schema)
                if model == response_model:
                    model_statuses.append(status_code)
                elif model != "ErrorResponse":
                    raise GenerationError(
                        f"unsupported response model {model!r} for {operation_id} status {status}"
                    )
            observed[operation_id] = (
                method.upper(),
                path,
                _ref_name(request_schema),
                response_model,
                tuple(sorted(model_statuses)),
            )
            expected_security = [{"UserToken": []}] if path.startswith("/api/v1/") else []
            if operation.get("security") != expected_security:
                raise GenerationError(f"unexpected security contract for {operation_id}")
            for response in operation.get("responses", {}).values():
                headers = response.get("headers", {}) if isinstance(response, dict) else {}
                if not {
                    "X-SouWen-API-Major",
                    "X-Request-ID",
                    "X-SouWen-Rollout-Mode",
                } <= set(headers):
                    raise GenerationError(f"missing canonical response headers for {operation_id}")
    if observed != EXPECTED_OPERATIONS:
        raise GenerationError(f"unexpected target operation set: {sorted(observed)}")
    expected_signatures = {
        (method, path, operation_id)
        for operation_id, (method, path, *_models) in EXPECTED_OPERATIONS.items()
    }
    if observed_signatures != expected_signatures:
        raise GenerationError(
            f"unexpected target operation signatures: {sorted(observed_signatures)}"
        )


def _literal(values: list[Any]) -> str:
    return f"Literal[{', '.join(repr(value) for value in values)}]"


def _annotation(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        name = _ref_name(schema)
        if name is None:
            raise GenerationError(f"invalid schema ref: {schema!r}")
        return name
    if "anyOf" in schema:
        variants = schema["anyOf"]
        if not isinstance(variants, list) or not variants:
            raise GenerationError(f"invalid anyOf: {schema!r}")
        annotations = [_annotation(variant) for variant in variants]
        return " | ".join(dict.fromkeys(annotations))
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            raise GenerationError(f"invalid enum: {schema!r}")
        return _literal(values)
    if "const" in schema:
        return _literal([schema["const"]])

    schema_type = schema.get("type")
    if schema_type == "null":
        return "None"
    if schema_type == "string":
        if schema.get("format") == "date-time":
            return "datetime"
        if schema.get("format") == "uri":
            return "AnyUrl"
        if schema.get("format") not in {None, "date-time", "uri"}:
            raise GenerationError(f"unsupported string format: {schema.get('format')}")
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise GenerationError(f"array items are required: {schema!r}")
        return f"list[{_annotation(items)}]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"dict[str, {_annotation(additional)}]"
        if not schema.get("properties"):
            return "dict[str, Any]"
        raise GenerationError("inline object models are not supported")
    if schema_type is None and set(schema) <= {"title"}:
        return "Any"
    raise GenerationError(f"unsupported schema shape: {schema!r}")


def _value_schema(schema: dict[str, Any]) -> dict[str, Any]:
    variants = schema.get("anyOf")
    if not isinstance(variants, list):
        return schema
    non_null = [variant for variant in variants if variant.get("type") != "null"]
    return non_null[0] if len(non_null) == 1 else schema


def _field_arguments(schema: dict[str, Any]) -> list[str]:
    value_schema = _value_schema(schema)
    mapping = (
        ("minLength", "min_length"),
        ("maxLength", "max_length"),
        ("minItems", "min_length"),
        ("maxItems", "max_length"),
        ("minimum", "ge"),
        ("maximum", "le"),
        ("exclusiveMinimum", "gt"),
        ("exclusiveMaximum", "lt"),
        ("pattern", "pattern"),
    )
    arguments = [
        f"{target}={value_schema[source]!r}" for source, target in mapping if source in value_schema
    ]
    if isinstance(schema.get("description"), str):
        arguments.append(f"description={schema['description']!r}")
    return arguments


def _field_line(name: str, schema: dict[str, Any], required: bool) -> str:
    annotation = _annotation(schema)
    arguments = _field_arguments(schema)
    if "default" in schema:
        default = schema["default"]
        if default == []:
            default_expr = "Field(default_factory=list"
            return f"    {name}: {annotation} = {default_expr}{', ' if arguments else ''}{', '.join(arguments)})"
        if default == {}:
            default_expr = "Field(default_factory=dict"
            return f"    {name}: {annotation} = {default_expr}{', ' if arguments else ''}{', '.join(arguments)})"
        if arguments:
            return f"    {name}: {annotation} = Field(default={default!r}, {', '.join(arguments)})"
        return f"    {name}: {annotation} = {default!r}"
    if required:
        if arguments:
            return f"    {name}: {annotation} = Field({', '.join(arguments)})"
        return f"    {name}: {annotation}"
    if "None" not in annotation.split(" | "):
        annotation = f"{annotation} | None"
    if arguments:
        return f"    {name}: {annotation} = Field(default=None, {', '.join(arguments)})"
    return f"    {name}: {annotation} = None"


def _generated_header(artifact_sha: str) -> list[str]:
    return [
        '"""Generated from contracts/openapi/souwen-openapi-2.0.0rc5.json; do not edit."""',
        "",
        f"# generator_version={GENERATOR_VERSION}",
        f"# openapi_sha256={artifact_sha}",
        "",
    ]


def _render_models(document: dict[str, Any], artifact_sha: str) -> str:
    schemas = document.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict) or not schemas:
        raise GenerationError("OpenAPI components.schemas must be a non-empty object")
    lines = _generated_header(artifact_sha)
    lines.extend(
        [
            "from __future__ import annotations",
            "",
            "from datetime import datetime",
            "from typing import Any, Literal",
            "",
            "from pydantic import AnyUrl, BaseModel, ConfigDict, Field",
            "",
            "",
            "class _StrictModel(BaseModel):",
            '    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)',
            "",
            "",
            "class _OpenModel(BaseModel):",
            '    model_config = ConfigDict(extra="allow", frozen=True, hide_input_in_errors=True)',
            "",
        ]
    )
    model_names: list[str] = []
    alias_names: list[str] = []
    for name, schema in schemas.items():
        if not isinstance(schema, dict):
            raise GenerationError(f"schema {name} must be an object")
        if schema.get("type") != "object":
            lines.extend(["", f"{name} = {_annotation(schema)}"])
            alias_names.append(name)
            continue
        base = "_StrictModel" if schema.get("additionalProperties") is False else "_OpenModel"
        lines.extend(["", "", f"class {name}({base}):"])
        description = schema.get("description")
        if isinstance(description, str):
            lines.append(f"    {description!r}")
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if not isinstance(properties, dict):
            raise GenerationError(f"schema {name}.properties must be an object")
        if not properties:
            lines.append("    pass")
        for field_name, field_schema in properties.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name):
                raise GenerationError(f"unsupported Python field name: {name}.{field_name}")
            if not isinstance(field_schema, dict):
                raise GenerationError(f"field schema must be an object: {name}.{field_name}")
            lines.append(_field_line(field_name, field_schema, field_name in required))
        model_names.append(name)
    lines.extend(["", ""])
    for name in model_names:
        lines.append(f"{name}.model_rebuild()")
    exported = sorted([*model_names, *alias_names])
    lines.extend(["", "", f"__all__ = {exported!r}", ""])
    return "\n".join(lines)


def _constant_name(operation_id: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", operation_id).upper()


def _render_operations(document: dict[str, Any], artifact_sha: str) -> str:
    lines = _generated_header(artifact_sha)
    lines.extend(
        [
            "from __future__ import annotations",
            "",
            "from typing import NamedTuple",
            "",
            f'SDK_VERSION = "{document["info"]["version"]}"',
            f"SUPPORTED_API_MAJOR = {document['x-souwen-api-major']}",
            f'OPENAPI_SHA256 = "{artifact_sha}"',
            "",
            "",
            "class Operation(NamedTuple):",
            "    method: str",
            "    path: str",
            "    request_model: str | None",
            "    response_model: str",
            "    response_statuses: tuple[int, ...]",
            "",
        ]
    )
    constants: list[str] = []
    for operation_id, value in EXPECTED_OPERATIONS.items():
        constant = _constant_name(operation_id)
        constants.append(constant)
        lines.append(f"{constant} = Operation{value!r}")
    lines.extend(
        [
            "",
            "OPERATIONS = {",
            *[
                f'    "{operation_id}": {_constant_name(operation_id)},'
                for operation_id in EXPECTED_OPERATIONS
            ],
            "}",
            "",
            "",
            f"__all__ = {sorted([*constants, 'OPENAPI_SHA256', 'OPERATIONS', 'Operation', 'SDK_VERSION', 'SUPPORTED_API_MAJOR'])!r}",
            "",
        ]
    )
    return "\n".join(lines)


def _rendered_files(document: dict[str, Any], artifact_payload: bytes) -> dict[str, bytes]:
    artifact_sha = hashlib.sha256(artifact_payload).hexdigest()
    rendered = {
        "_generated_models.py": _render_models(document, artifact_sha),
        "_generated_operations.py": _render_operations(document, artifact_sha),
    }
    formatted: dict[str, bytes] = {}
    for name, source in rendered.items():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "ruff", "format", "--stdin-filename", name, "-"],
                input=source,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise GenerationError(f"cannot run pinned Ruff formatter: {exc}") from exc
        if result.returncode != 0:
            raise GenerationError(
                f"cannot format generated binding {name}: {result.stderr.strip()}"
            )
        formatted[name] = result.stdout.encode("utf-8")
    return formatted


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="write generated SDK bindings")
    action.add_argument("--check", action="store_true", help="verify generated SDK bindings")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document, artifact_payload = _load_document(args.artifact)
        _validate_document(document)
        rendered = _rendered_files(document, artifact_payload)
    except GenerationError as exc:
        print(f"Python SDK generation failed: {exc}", file=sys.stderr)
        return 2

    if args.write:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, payload in rendered.items():
            (args.output / name).write_bytes(payload)
        print(f"wrote {len(rendered)} Python SDK binding files to {args.output}")
        return 0

    stale = [
        name
        for name, payload in rendered.items()
        if not (args.output / name).is_file() or (args.output / name).read_bytes() != payload
    ]
    if stale:
        print(f"generated Python SDK bindings are stale: {', '.join(stale)}", file=sys.stderr)
        return 1
    print(f"generated Python SDK bindings are reproducible: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
