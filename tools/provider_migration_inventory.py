"""Generate the deterministic B0 Provider v2 migration inventory.

The registry remains the source of truth for legacy source metadata.  This
tool only reads registry declarations and manifest source files; it does not
load provider clients, read configuration, or access the network.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

ARTIFACT_DIR = REPO_ROOT / "docs" / "internal" / "provider-migrations"
DEFAULT_JSON_PATH = ARTIFACT_DIR / "b0-inventory.json"
DEFAULT_MARKDOWN_PATH = ARTIFACT_DIR / "b0-inventory.md"
SCHEMA_VERSION = 1
GENERATOR_VERSION = "b0-provider-migration-inventory-v1"
SAMPLE_BATCH = "sample"
BATCH_ORDER = ("batch-1", "batch-2", "batch-3", "batch-4", "batch-5", "batch-6")
UNCLASSIFIED_BATCH = "unclassified"
EXPECTED_COUNTS = {
    SAMPLE_BATCH: 6,
    "batch-1": 14,
    "batch-2": 14,
    "batch-3": 33,
    "batch-4": 11,
    "batch-5": 29,
    "batch-6": 3,
    UNCLASSIFIED_BATCH: 0,
}
BATCH_EXCEPTIONS = {
    "arxiv_fulltext": (
        "batch-1",
        "paper full-text companion source; migrate with paper/patent no-key batch",
    ),
}
SAMPLE_SOURCE_IDS = frozenset(
    {
        "builtin",
        "eric",
        "openalex",
        "patentsview",
        "uniapi_ark_annotations_deepseek_v3_2_251201",
        "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
    }
)
NON_REST_SPEC_EXCEPTIONS = {
    "builtin": "capability-specific Fetch Provider is covered by deterministic conformance",
    "uniapi_ark_annotations_deepseek_v3_2_251201": (
        "capability-specific LLM Search Provider is covered by deterministic conformance"
    ),
    "uniapi_ark_annotations_doubao_seed_2_0_lite_260428": (
        "capability-specific LLM Search Provider is covered by deterministic conformance"
    ),
}


def _static_string(node: ast.expr, constants: dict[str, str]) -> str | None:
    """Resolve only a literal or a module-level string constant."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _is_provider_manifest_validate(call: ast.Call) -> bool:
    """Return whether *call* is the static ProviderManifest declaration call."""

    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "model_validate"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "ProviderManifest"
    )


def _manifest_id_expression(call: ast.Call) -> ast.expr | None:
    """Extract only the top-level ``id`` from a manifest literal."""

    if not _is_provider_manifest_validate(call) or len(call.args) != 1:
        return None
    payload = call.args[0]
    if not isinstance(payload, ast.Dict):
        return None
    for key, value in zip(payload.keys, payload.values, strict=True):
        if isinstance(key, ast.Constant) and key.value == "id":
            return value
    return None


def _manifest_adapters_expression(call: ast.Call) -> ast.expr | None:
    """Extract only the top-level ``adapters`` declaration from a manifest literal."""

    if not _is_provider_manifest_validate(call) or len(call.args) != 1:
        return None
    payload = call.args[0]
    if not isinstance(payload, ast.Dict):
        return None
    for key, value in zip(payload.keys, payload.values, strict=True):
        if isinstance(key, ast.Constant) and key.value == "adapters":
            return value
    return None


def _manifest_targets_from_tree(tree: ast.Module, path: Path) -> dict[str, dict[str, Any]]:
    """Read static manifest ID and adapter identity declarations without imports.

    A manifest may be declared directly or through a tiny local factory (the
    immutable UniAPI manifests).  Factory arguments are accepted only when the
    same parameter is the top-level ``id`` passed to ``model_validate``.  The
    same restriction is applied to the top-level ``adapters`` entries; no
    arbitrary string constants elsewhere in a manifest are considered source
    identities.
    """

    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    targets: dict[str, dict[str, Any]] = {}
    factory_id_parameters: dict[str, str] = {}
    functions: dict[str, ast.FunctionDef] = {}

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        functions[node.name] = node
        parameters = {argument.arg for argument in node.args.args}
        expressions = [
            expression
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            if (expression := _manifest_id_expression(child)) is not None
        ]
        if len(expressions) == 1 and isinstance(expressions[0], ast.Name):
            parameter = expressions[0].id
            if parameter in parameters:
                factory_id_parameters[node.name] = parameter

    def adapter_rows(
        expression: ast.expr | None, substitutions: dict[str, str]
    ) -> list[dict[str, str]]:
        if not isinstance(expression, (ast.List, ast.Tuple)):
            return []
        rows: list[dict[str, str]] = []
        for item in expression.elts:
            if not isinstance(item, ast.Dict):
                continue
            fields = {
                key.value: value
                for key, value in zip(item.keys, item.values, strict=True)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            adapter_id = _static_string(fields.get("id"), {**constants, **substitutions})
            capability = _static_string(fields.get("capability"), {**constants, **substitutions})
            if adapter_id is not None and capability is not None:
                rows.append({"adapter_id": adapter_id, "capability": capability})
        return rows

    def add_target(call: ast.Call, substitutions: dict[str, str]) -> None:
        identifier = _manifest_id_expression(call)
        manifest_id = (
            _static_string(identifier, {**constants, **substitutions})
            if identifier is not None
            else None
        )
        adapters = adapter_rows(_manifest_adapters_expression(call), substitutions)
        if manifest_id is None or not adapters:
            return
        targets[manifest_id] = {
            "package": ".".join(path.relative_to(SRC_ROOT).parent.parts),
            "manifest_path": path.relative_to(REPO_ROOT).as_posix(),
            "adapters": adapters,
        }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        expression = _manifest_id_expression(node)
        if expression is not None:
            literal = _static_string(expression, constants)
            if literal is not None:
                add_target(node, {})
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in factory_id_parameters:
            continue
        function = node.func.id
        parameter = factory_id_parameters[function]
        function_node = functions.get(function)
        if function_node is None:
            continue
        position = next(
            (
                index
                for index, argument in enumerate(function_node.args.args)
                if argument.arg == parameter
            ),
            None,
        )
        if position is not None and len(node.args) > position:
            literal = _static_string(node.args[position], constants)
            if literal is not None:
                validation_call = next(
                    (
                        child
                        for child in ast.walk(function_node)
                        if isinstance(child, ast.Call)
                        and _manifest_id_expression(child) is not None
                    ),
                    None,
                )
                if validation_call is not None:
                    add_target(validation_call, {parameter: literal})
    return targets


def _manifest_targets() -> dict[str, dict[str, Any]]:
    """Return static ProviderManifest target declarations without imports."""

    root = SRC_ROOT / "souwen" / "providers"
    targets: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("manifest.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for manifest_id, target in _manifest_targets_from_tree(tree, path).items():
            if manifest_id in targets:
                raise ValueError(f"duplicate ProviderManifest ID: {manifest_id}")
            targets[manifest_id] = target
    return targets


def _manifest_ids() -> frozenset[str]:
    """Return static ProviderManifest identity values without importing providers."""

    return frozenset(_manifest_targets())


def _target_spec_reference(source_id: str, target: dict[str, Any]) -> dict[str, str | None]:
    """Locate a same-package static Provider specification without importing it."""

    manifest_path = REPO_ROOT / target["manifest_path"]
    spec_path = manifest_path.with_name("spec.py")
    if spec_path.is_file():
        tree = ast.parse(spec_path.read_text(encoding="utf-8"), filename=str(spec_path))
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }
        for node in tree.body:
            if not (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "RestJsonProviderSpec"
            ):
                continue
            provider_id = next(
                (
                    _static_string(keyword.value, constants)
                    for keyword in node.value.keywords
                    if keyword.arg == "provider_id"
                ),
                None,
            )
            if provider_id == source_id:
                return {
                    "target_spec_identity": f"{target['package']}.spec.{node.targets[0].id}",
                    "target_spec_path": spec_path.relative_to(REPO_ROOT).as_posix(),
                    "target_spec_reason": None,
                }
    exception_reason = NON_REST_SPEC_EXCEPTIONS.get(source_id)
    if exception_reason is not None:
        return {
            "target_spec_identity": None,
            "target_spec_path": None,
            "target_spec_reason": exception_reason,
        }
    return {
        "target_spec_identity": None,
        "target_spec_path": None,
        "target_spec_reason": "no static Provider v2 specification declared in target package",
    }


def _target_fields(
    source_id: str, manifest_id: str | None, manifest_targets: dict[str, dict[str, Any]]
) -> dict[str, str | None]:
    """Return target contract fields for a migrated source or explicit pending nulls."""

    if manifest_id is None:
        return {
            "target_package": None,
            "target_manifest_id": None,
            "target_adapter_id": None,
            "target_capability": None,
            "target_spec_identity": None,
            "target_spec_path": None,
            "target_spec_reason": None,
        }
    target = manifest_targets[manifest_id]
    adapters = [adapter for adapter in target["adapters"] if adapter["adapter_id"] == manifest_id]
    adapter = adapters[0] if len(adapters) == 1 else target["adapters"][0]
    return {
        "target_package": target["package"],
        "target_manifest_id": manifest_id,
        "target_adapter_id": adapter["adapter_id"],
        "target_capability": adapter["capability"],
        **_target_spec_reference(source_id, target),
    }


def _manifest_id_for_source(source_id: str, manifest_ids: frozenset[str]) -> str | None:
    """Match a source to its existing manifest identity using stable naming only."""

    for candidate in (source_id, f"{source_id}-search", f"{source_id}-fetch"):
        if candidate in manifest_ids:
            return candidate
    return None


def classify_source(source_id: str, adapter: Any) -> tuple[str, str]:
    """Assign the stable B0 migration batch from registry metadata only.

    Existing or future manifests never decide this batch.  That preserves the
    original delivery batch after an implementation becomes migrated.
    """

    if source_id in SAMPLE_SOURCE_IDS:
        return SAMPLE_BATCH, "B0 sample source allocated before planned batches"
    if source_id in BATCH_EXCEPTIONS:
        return BATCH_EXCEPTIONS[source_id]
    if adapter.domain in {"paper", "patent"}:
        batch = "batch-1" if adapter.resolved_auth_requirement == "none" else "batch-2"
        return batch, "paper/patent grouped by auth requirement"
    if adapter.integration == "scraper":
        return "batch-5", "scraper integration"
    if adapter.domain in {"book", "research_output"}:
        return "batch-4", "book or research-output domain"
    if adapter.integration == "self_hosted":
        return "batch-6", "self-hosted integration"
    if adapter.domain in {
        "web",
        "social",
        "video",
        "knowledge",
        "developer",
        "cn_tech",
        "office",
        "archive",
        "fetch",
    }:
        return "batch-3", "remaining web-facing integration"
    return UNCLASSIFIED_BATCH, "no approved B0 batch rule matched"


def _loader_evidence(adapter: Any) -> str:
    """Return a non-executing loader identity for review, never the client itself."""

    return str(
        getattr(adapter.client_loader, "__qualname__", None)
        or getattr(adapter.client_loader, "__name__", None)
        or type(adapter.client_loader).__qualname__
    )


def build_inventory() -> dict[str, Any]:
    """Build the stable, value-free inventory from the built-in registry."""

    from souwen.registry import all_adapters

    manifest_targets = _manifest_targets()
    manifest_ids = frozenset(manifest_targets)
    records: list[dict[str, Any]] = []
    for source_id, adapter in sorted(all_adapters().items()):
        manifest_id = _manifest_id_for_source(source_id, manifest_ids)
        batch, classification_reason = classify_source(source_id, adapter)
        target_fields = _target_fields(source_id, manifest_id, manifest_targets)
        if manifest_id is None:
            migration_status = "pending"
        elif (
            target_fields["target_spec_identity"] is not None
            or source_id in NON_REST_SPEC_EXCEPTIONS
        ):
            migration_status = "migrated"
        else:
            migration_status = "incomplete"
        records.append(
            {
                "source_id": source_id,
                "batch": batch,
                "classification_reason": classification_reason,
                "migration_status": migration_status,
                "domain": adapter.domain,
                "capabilities": sorted(adapter.capabilities),
                "integration": adapter.integration,
                "auth_requirement": adapter.resolved_auth_requirement,
                "credential_fields": list(adapter.resolved_credential_fields),
                "legacy_loader": _loader_evidence(adapter),
                "provider_manifest_id": manifest_id,
                **target_fields,
            }
        )

    counts = Counter(record["batch"] for record in records)
    actual_counts = {key: counts[key] for key in (*EXPECTED_COUNTS,)}
    if actual_counts != EXPECTED_COUNTS:
        raise ValueError(
            f"B0 batch classification drift: actual={actual_counts}, expected={EXPECTED_COUNTS}"
        )
    status_counts = Counter(record["migration_status"] for record in records)
    registry_metadata = [
        {
            key: record[key]
            for key in (
                "source_id",
                "domain",
                "capabilities",
                "integration",
                "auth_requirement",
                "credential_fields",
                "legacy_loader",
                "target_package",
                "target_manifest_id",
                "target_adapter_id",
                "target_capability",
                "target_spec_identity",
                "target_spec_path",
                "target_spec_reason",
            )
        }
        for record in records
    ]
    manifest_metadata = [
        {
            "source_id": record["source_id"],
            "provider_manifest_id": record["provider_manifest_id"],
        }
        for record in records
    ]

    def fingerprint(value: Any) -> str:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    registry_metadata_sha256 = fingerprint(registry_metadata)
    provider_manifest_ids_sha256 = fingerprint(manifest_metadata)
    source_fingerprint = {
        "registry_metadata_sha256": registry_metadata_sha256,
        "provider_manifest_ids_sha256": provider_manifest_ids_sha256,
        "input_sha256": fingerprint(
            {
                "registry_metadata_sha256": registry_metadata_sha256,
                "provider_manifest_ids_sha256": provider_manifest_ids_sha256,
            }
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "source_fingerprint": source_fingerprint,
        "registry_count": len(records),
        "batch_counts": actual_counts,
        "status_counts": {
            "migrated": status_counts["migrated"],
            "pending": status_counts["pending"],
            "incomplete": status_counts["incomplete"],
        },
        "classification_complete": (
            counts[UNCLASSIFIED_BATCH] == 0 and status_counts["incomplete"] == 0
        ),
        "registry_sha256": fingerprint(records),
        "records": records,
    }


def render_json(inventory: dict[str, Any] | None = None) -> str:
    return (
        json.dumps(inventory or build_inventory(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def render_markdown(inventory: dict[str, Any] | None = None) -> str:
    data = inventory or build_inventory()
    counts = data["batch_counts"]
    lines = [
        "# B0 Provider v2 migration inventory",
        "",
        "This file is generated by `tools/provider_migration_inventory.py`; do not edit it by hand.",
        "It reads registry declarations and manifest source files only. It never loads clients, reads",
        "configuration, or includes credential values.",
        "",
        f"- Schema version: `{data['schema_version']}`",
        f"- Generator version: `{data['generator_version']}`",
        f"- Registry sources: `{data['registry_count']}`",
        f"- Registry output fingerprint: `{data['registry_sha256']}`",
        f"- Registry input fingerprint: `{data['source_fingerprint']['registry_metadata_sha256']}`",
        "- Provider manifest input fingerprint: "
        f"`{data['source_fingerprint']['provider_manifest_ids_sha256']}`",
        f"- Combined input fingerprint: `{data['source_fingerprint']['input_sha256']}`",
        "",
        "## Batch counts",
        "",
        "| Batch | Sources |",
        "|---|---:|",
        *[
            f"| `{batch}` | {counts[batch]} |"
            for batch in (SAMPLE_BATCH, *BATCH_ORDER, UNCLASSIFIED_BATCH)
        ],
        "",
        "## Migration status counts",
        "",
        "| Status | Sources |",
        "|---|---:|",
        *[f"| `{status}` | {count} |" for status, count in data["status_counts"].items()],
        "",
        "## Source records",
        "",
        "| Source | Batch | Status | Classification reason | Domain | Capabilities | Auth | Integration | Legacy loader | Manifest |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in data["records"]:
        lines.append(
            "| `{source_id}` | `{batch}` | `{status}` | {reason} | `{domain}` | {capabilities} | "
            "`{auth}` | `{integration}` | `{loader}` | {manifest} |".format(
                source_id=record["source_id"],
                batch=record["batch"],
                status=record["migration_status"],
                reason=record["classification_reason"],
                domain=record["domain"],
                capabilities=", ".join(f"`{item}`" for item in record["capabilities"]),
                auth=record["auth_requirement"],
                integration=record["integration"],
                loader=record["legacy_loader"],
                manifest=(
                    f"`{record['provider_manifest_id']}`" if record["provider_manifest_id"] else "—"
                ),
            )
        )
    return "\n".join(lines) + "\n"


def _check(path: Path, expected: str) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="write controlled JSON and Markdown artifacts"
    )
    parser.add_argument(
        "--check", action="store_true", help="fail when controlled artifacts are stale"
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail for an unclassified source or a manifest without reviewed spec/conformance",
    )
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    args = parser.parse_args(argv)
    if args.write and args.check:
        parser.error("--write and --check are mutually exclusive")

    inventory = build_inventory()
    json_text = render_json(inventory)
    markdown_text = render_markdown(inventory)
    if args.write:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json_text, encoding="utf-8")
        args.markdown_path.write_text(markdown_text, encoding="utf-8")
        print(f"WROTE: {args.json_path}")
        print(f"WROTE: {args.markdown_path}")
    elif args.check:
        stale = [
            str(path)
            for path, expected in ((args.json_path, json_text), (args.markdown_path, markdown_text))
            if not _check(path, expected)
        ]
        if stale:
            print("STALE: " + ", ".join(stale), file=sys.stderr)
            return 1
        if args.require_complete and not inventory["classification_complete"]:
            print(
                "INCOMPLETE: B0 inventory has unclassified or partial migrations", file=sys.stderr
            )
            return 1
        print(f"OK: {inventory['registry_count']} sources in B0 inventory")
    else:
        print(markdown_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
