#!/usr/bin/env python3
"""Validate optional SouWen plugin manifest files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from souwen.registry.adapter import (  # noqa: E402
    AUTH_REQUIREMENTS,
    CAPABILITIES,
    CATALOG_VISIBILITIES,
    DISTRIBUTIONS,
    DOMAINS,
    FETCH_DOMAIN,
    INTEGRATIONS,
    OPTIONAL_CREDENTIAL_EFFECTS,
    RISK_LEVELS,
    RISK_REASONS,
    SOURCE_CATEGORIES,
    STABILITIES,
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)?$")


def _require_dict(value: Any, path: str, issues: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    issues.append(f"{path}: expected object")
    return {}


def _require_str(value: Any, path: str, issues: list[str]) -> str:
    if isinstance(value, str) and value:
        return value
    issues.append(f"{path}: expected non-empty string")
    return ""


def _optional_str(value: Any, path: str, issues: list[str]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    issues.append(f"{path}: expected string or null")
    return None


def _string_list(value: Any, path: str, issues: list[str]) -> list[str]:
    if not isinstance(value, list):
        issues.append(f"{path}: expected list")
        return []
    out: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str):
            issues.append(f"{path}[{index}]: expected string")
            continue
        if item in seen:
            issues.append(f"{path}: duplicate value {item!r}")
            continue
        seen.add(item)
        out.append(item)
    return out


def _check_enum(
    value: Any,
    allowed: set[str] | frozenset[str],
    path: str,
    issues: list[str],
    *,
    allow_null: bool = False,
) -> str | None:
    if allow_null and value is None:
        return None
    if isinstance(value, str) and value in allowed:
        return value
    allowed_text = ", ".join(sorted(allowed))
    if allow_null:
        allowed_text = f"{allowed_text}, null"
    issues.append(f"{path}: expected one of {allowed_text}")
    return None


def _resolved_auth(adapter: dict[str, Any]) -> str:
    auth = adapter.get("auth_requirement")
    if isinstance(auth, str):
        return auth
    needs_config = adapter.get("needs_config")
    integration = adapter.get("integration")
    config_field = adapter.get("config_field")
    credential_fields = adapter.get("credential_fields") or []
    if isinstance(needs_config, bool):
        if needs_config:
            return "self_hosted" if integration == "self_hosted" else "required"
        return "optional" if config_field or credential_fields else "none"
    if integration == "self_hosted":
        return "self_hosted"
    if config_field is None:
        return "none"
    if integration == "official_api":
        return "required"
    return "optional"


def validate_adapter(adapter: dict[str, Any], path: str) -> list[str]:
    issues: list[str] = []
    allowed_keys = {
        "name",
        "domain",
        "integration",
        "description",
        "config_field",
        "methods",
        "extra_domains",
        "default_enabled",
        "default_for",
        "tags",
        "needs_config",
        "auth_requirement",
        "credential_fields",
        "optional_credential_effect",
        "risk_level",
        "risk_reasons",
        "distribution",
        "package_extra",
        "stability",
        "usage_note",
        "category",
        "catalog_visibility",
    }
    for key in sorted(set(adapter) - allowed_keys):
        issues.append(f"{path}.{key}: unknown field")

    name = _require_str(adapter.get("name"), f"{path}.name", issues)
    if name and NAME_RE.fullmatch(name) is None:
        issues.append(f"{path}.name: must match {NAME_RE.pattern}")

    _require_str(adapter.get("description"), f"{path}.description", issues)
    domain = _check_enum(
        adapter.get("domain"),
        set(DOMAINS) | {FETCH_DOMAIN},
        f"{path}.domain",
        issues,
    )
    _check_enum(adapter.get("integration"), INTEGRATIONS, f"{path}.integration", issues)
    _optional_str(adapter.get("config_field"), f"{path}.config_field", issues)

    methods = _string_list(adapter.get("methods"), f"{path}.methods", issues)
    if not methods:
        issues.append(f"{path}.methods: must include at least one capability")
    for method in methods:
        if CAPABILITY_RE.fullmatch(method) is None:
            issues.append(f"{path}.methods: invalid capability format {method!r}")
        elif method not in CAPABILITIES and ":" not in method:
            issues.append(f"{path}.methods: unknown non-namespaced capability {method!r}")

    extra_domains = _string_list(adapter.get("extra_domains", []), f"{path}.extra_domains", issues)
    for extra_domain in extra_domains:
        if extra_domain != FETCH_DOMAIN:
            issues.append(f"{path}.extra_domains: only {FETCH_DOMAIN!r} is allowed")

    if not isinstance(adapter.get("default_enabled", True), bool):
        issues.append(f"{path}.default_enabled: expected boolean")
    needs_config = adapter.get("needs_config")
    if needs_config is not None and not isinstance(needs_config, bool):
        issues.append(f"{path}.needs_config: expected boolean or null")

    auth_requirement = _check_enum(
        adapter.get("auth_requirement"),
        AUTH_REQUIREMENTS,
        f"{path}.auth_requirement",
        issues,
        allow_null=True,
    )
    credential_fields = _string_list(
        adapter.get("credential_fields", []),
        f"{path}.credential_fields",
        issues,
    )
    effective_auth = auth_requirement or _resolved_auth(adapter)
    if effective_auth == "none" and credential_fields:
        issues.append(f"{path}.credential_fields: auth_requirement='none' cannot use credentials")
    if effective_auth in {"required", "self_hosted"}:
        config_field = adapter.get("config_field")
        if not config_field and not credential_fields:
            issues.append(
                f"{path}: auth_requirement={effective_auth!r} requires config_field "
                "or credential_fields"
            )

    optional_effect = _check_enum(
        adapter.get("optional_credential_effect"),
        OPTIONAL_CREDENTIAL_EFFECTS,
        f"{path}.optional_credential_effect",
        issues,
        allow_null=True,
    )
    if optional_effect is not None and effective_auth != "optional":
        issues.append(f"{path}.optional_credential_effect: only valid for optional auth")

    risk_level = _check_enum(
        adapter.get("risk_level", "low"),
        RISK_LEVELS,
        f"{path}.risk_level",
        issues,
    )
    risk_reasons = _string_list(adapter.get("risk_reasons", []), f"{path}.risk_reasons", issues)
    for reason in risk_reasons:
        if reason not in RISK_REASONS:
            issues.append(f"{path}.risk_reasons: unknown reason {reason!r}")
    if risk_level == "high" and "external_plugin" not in adapter.get("tags", []):
        issues.append(f"{path}.tags: high-risk external adapters should include 'external_plugin'")

    _check_enum(
        adapter.get("distribution", "plugin"),
        DISTRIBUTIONS,
        f"{path}.distribution",
        issues,
    )
    _optional_str(adapter.get("package_extra"), f"{path}.package_extra", issues)
    _check_enum(adapter.get("stability", "stable"), STABILITIES, f"{path}.stability", issues)
    _optional_str(adapter.get("usage_note"), f"{path}.usage_note", issues)
    _check_enum(
        adapter.get("category"),
        SOURCE_CATEGORIES,
        f"{path}.category",
        issues,
        allow_null=True,
    )
    _check_enum(
        adapter.get("catalog_visibility", "public"),
        CATALOG_VISIBILITIES,
        f"{path}.catalog_visibility",
        issues,
    )

    default_for = _string_list(adapter.get("default_for", []), f"{path}.default_for", issues)
    domains = {domain} if domain else set()
    domains.update(extra_domains)
    for item in default_for:
        if ":" not in item:
            issues.append(f"{path}.default_for: {item!r} must be 'domain:capability'")
            continue
        default_domain, default_capability = item.split(":", 1)
        if default_domain not in set(DOMAINS) | {FETCH_DOMAIN}:
            issues.append(f"{path}.default_for: unknown domain {default_domain!r}")
        if default_capability not in CAPABILITIES:
            issues.append(f"{path}.default_for: unknown capability {default_capability!r}")
        if default_capability not in methods:
            issues.append(f"{path}.default_for: {item!r} is not listed in methods")
        if default_domain not in domains:
            issues.append(f"{path}.default_for: {item!r} is outside adapter domains")

    _string_list(adapter.get("tags", []), f"{path}.tags", issues)
    return issues


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    allowed_keys = {
        "$schema",
        "schema_version",
        "name",
        "entry_point",
        "version",
        "api_version",
        "min_souwen_version",
        "max_souwen_version",
        "description",
        "adapters",
    }
    for key in sorted(set(manifest) - allowed_keys):
        issues.append(f"{key}: unknown field")

    if manifest.get("schema_version") != 1:
        issues.append("schema_version: expected 1")

    name = _require_str(manifest.get("name"), "name", issues)
    if name and NAME_RE.fullmatch(name) is None:
        issues.append(f"name: must match {NAME_RE.pattern}")

    entry_point = _require_str(manifest.get("entry_point"), "entry_point", issues)
    if entry_point and ENTRY_POINT_RE.fullmatch(entry_point) is None:
        issues.append("entry_point: expected 'module.path:attribute'")

    _require_str(manifest.get("version"), "version", issues)
    _optional_str(manifest.get("api_version", "1"), "api_version", issues)
    _optional_str(manifest.get("min_souwen_version"), "min_souwen_version", issues)
    _optional_str(manifest.get("max_souwen_version"), "max_souwen_version", issues)
    if "description" in manifest:
        _require_str(manifest.get("description"), "description", issues)

    adapters = manifest.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        issues.append("adapters: expected non-empty list")
        return issues

    adapter_names: set[str] = set()
    for index, value in enumerate(adapters):
        adapter = _require_dict(value, f"adapters[{index}]", issues)
        if not adapter:
            continue
        adapter_name = adapter.get("name")
        if isinstance(adapter_name, str):
            if adapter_name in adapter_names:
                issues.append(f"adapters[{index}].name: duplicate adapter {adapter_name!r}")
            adapter_names.add(adapter_name)
        issues.extend(validate_adapter(adapter, f"adapters[{index}]"))

    return issues


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: manifest root must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to souwen-plugin.json")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    issues = validate_manifest(manifest)
    if issues:
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"OK: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
