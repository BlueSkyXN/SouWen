from __future__ import annotations

import ast
import json
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from souwen.config.loader import _NESTED_CONFIG_FIELDS
from souwen.config.models import SouWenConfig
from souwen.plugin import ENTRY_POINT_GROUP, Plugin
from souwen.registry.adapter import CAPABILITIES, DOMAINS, FETCH_DOMAIN, MethodSpec, SourceAdapter
from souwen.registry.views import all_adapters


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests/contracts/fixtures/provider_directory_current_v1.json"


@pytest.fixture(scope="module")
def current_contract() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _imported_modules(relative_path: str) -> set[str]:
    tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None
    }


def test_fixture_is_parseable_and_current_only(current_contract: dict[str, object]) -> None:
    assert current_contract["fixture_version"] == 1
    assert current_contract["scope"] == "current_only"
    assert current_contract["target_claims_excluded"] == [
        "provider_extension_v2_implemented",
        "yaml_revision_workflow_implemented",
        "directory_target_dependency_rules_implemented",
    ]
    assert json.loads(json.dumps(current_contract, sort_keys=True)) == current_contract


def test_fixture_matches_current_registry_objects(current_contract: dict[str, object]) -> None:
    registry = current_contract["registry"]
    assert isinstance(registry, dict)
    assert registry["adapter_type"] == SourceAdapter.__name__
    assert registry["method_spec_type"] == MethodSpec.__name__
    assert registry["fetch_domain"] == FETCH_DOMAIN
    assert registry["standard_capabilities"] == sorted(CAPABILITIES)
    assert registry["domains"] == sorted(DOMAINS)

    assert is_dataclass(SourceAdapter)
    assert is_dataclass(MethodSpec)
    assert SourceAdapter.__dataclass_params__.frozen
    assert MethodSpec.__dataclass_params__.frozen
    assert set(registry["required_adapter_fields"]) <= {
        field.name for field in fields(SourceAdapter)
    }
    assert set(registry["required_method_spec_fields"]) <= {
        field.name for field in fields(MethodSpec)
    }

    adapters = all_adapters()
    representative_sources = registry["representative_sources"]
    assert isinstance(representative_sources, dict)
    for source_name, expected_capabilities in representative_sources.items():
        assert source_name in adapters
        assert sorted(adapters[source_name].capabilities) == expected_capabilities


def test_fixture_matches_current_plugin_and_configuration(
    current_contract: dict[str, object],
) -> None:
    plugin = current_contract["legacy_plugin"]
    config = current_contract["configuration"]
    assert isinstance(plugin, dict)
    assert isinstance(config, dict)

    assert plugin["entry_point_group"] == ENTRY_POINT_GROUP
    assert set(plugin["accepted_entry_shapes"]) == {
        Plugin.__name__,
        SourceAdapter.__name__,
        "list_or_tuple_of_SourceAdapter",
        "zero_argument_factory",
    }
    assert plugin["runtime_registry_mutation"] is True
    assert set(config["required_model_fields"]) <= set(SouWenConfig.model_fields)
    assert config["nested_loader_fields"] == sorted(_NESTED_CONFIG_FIELDS)
    assert config["precedence_high_to_low"] == [
        "environment",
        "project_yaml",
        "user_yaml",
        "dotenv",
        "defaults",
    ]

    loader_source = (REPO_ROOT / "src/souwen/config/loader.py").read_text(encoding="utf-8")
    assert loader_source.index('Path("souwen.yaml")') < loader_source.index(
        'Path("~/.config/souwen/config.yaml")'
    )
    assert loader_source.index("kwargs: dict = _load_dotenv_config()") < loader_source.index(
        "kwargs.update(_load_yaml_config())"
    )
    assert loader_source.index("kwargs.update(_load_yaml_config())") < loader_source.index(
        "kwargs.update(_load_env_mapping(dict(os.environ)))"
    )

    config_route_source = (REPO_ROOT / "src/souwen/server/routes/admin/config.py").read_text(
        encoding="utf-8"
    )
    sources_route_source = (REPO_ROOT / "src/souwen/server/routes/admin/sources.py").read_text(
        encoding="utf-8"
    )
    markers = config["current_admin_markers"]
    assert isinstance(markers, dict)
    assert markers["yaml_atomic_write_function"] in config_route_source
    assert markers["source_in_memory_assignment"] in sources_route_source


def test_fixture_matches_observed_directory_import_edges(
    current_contract: dict[str, object],
) -> None:
    edges = current_contract["directory_import_edges"]
    assert isinstance(edges, list)
    imported_by_path: dict[str, set[str]] = {}
    for edge in edges:
        assert isinstance(edge, dict)
        source_path = edge["from"]
        if source_path not in imported_by_path:
            imported_by_path[source_path] = _imported_modules(source_path)
        assert edge["to"] in imported_by_path[source_path]
