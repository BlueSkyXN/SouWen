from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hfs_v2_1_registry_is_preview_source_lane_and_registry_only() -> None:
    manifest_text = (REPO_ROOT / "hfs-dev.toml").read_text(encoding="utf-8")
    manifest = tomllib.loads(manifest_text)

    assert manifest["standard"] == "2.1"
    assert manifest["project"] == "SouWen"
    assert manifest["space"] == "BlueSkyXN/SouWen"
    assert manifest["project_class"] == "preview"
    assert manifest["target_role"] == "primary"
    assert manifest["sovereignty"] == "sovereign"
    assert manifest["lane"] == "source"
    assert manifest["version_source"] == "commit"
    assert manifest["env_file"] == ".env"
    assert manifest["secret_files"] == ["local/credentials/souwen-hfs.yaml"]
    assert manifest["operation_mode"] == "registry-only"
    assert manifest["dist_bucket"] == ""
    assert manifest["variables"] == []
    assert set(manifest["secrets"]) == {
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_CONFIG_B64",
        "UNIAPI_API_KEY",
    }
    assert set(manifest["workflow_owned_secrets"]) == set(manifest["secrets"])
    assert manifest["workflow_owned_variables"] == ["SOUWEN_WRAPPER_SHA"]
    assert any(item.startswith("generic-sync-disabled =") for item in manifest["deviations"])
    assert any(item.startswith("workflow-owned-settings =") for item in manifest["deviations"])
    assert any(
        item.startswith("workflow-generated-provenance =") for item in manifest["deviations"]
    )


def test_hfs_local_fact_sources_are_ignored_but_templates_remain_trackable() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    for pattern in (
        ".env",
        ".env.*",
        "!.env.example",
        "!.env.sample",
        "!.env.template",
        "config.toml",
        "/souwen.yaml",
        "local/",
    ):
        assert pattern in ignore

    assert (REPO_ROOT / ".env.example").is_file()
    assert (REPO_ROOT / "souwen.example.yaml").is_file()


def test_hfs_settings_remain_owned_by_candidate_pinned_workflow() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy-hf-space.yml").read_text(encoding="utf-8")
    manifest = tomllib.loads((REPO_ROOT / "hfs-dev.toml").read_text(encoding="utf-8"))
    managed_block = workflow.split("managed = {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    managed_pairs = re.findall(
        r'"([A-Z][A-Z0-9_]+)": os\.environ\["([A-Z][A-Z0-9_]+)"\]',
        managed_block,
    )

    assert managed_pairs
    assert all(key == env_name for key, env_name in managed_pairs)
    assert {key for key, _env_name in managed_pairs} == set(manifest["secrets"])
    assert "SOUWEN_CONFIG_B64: ${{ secrets.SOUWEN_CONFIG_B64 }}" in workflow
    assert "UNIAPI_API_KEY: ${{ secrets.UNIAPI_API_KEY }}" in workflow
    assert "api.add_space_secret(" in workflow
    assert "Managed Space Secret names:" in workflow
    assert "actual_names != expected_names" in workflow
    assert "api.delete_space_secret" not in workflow
    assert 'key="SOUWEN_WRAPPER_SHA"' in workflow
    assert "SOUWEN_WRAPPER_SHA variable readback mismatch" in workflow
    assert "candidate_sha" in workflow
    assert "parent_commit" in workflow
