from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hfs_v2_registry_is_source_lane_and_registry_only() -> None:
    manifest = (REPO_ROOT / "hfs-dev.toml").read_text(encoding="utf-8")

    for declaration in (
        'standard = "2.0"',
        'project = "SouWen"',
        'space = "BlueSkyXN/SouWen"',
        'sovereignty = "sovereign"',
        'lane = "source"',
        'version_source = "commit"',
        'operation_mode = "registry-only"',
        'dist_bucket = ""',
        "secrets = []",
        "variables = []",
    ):
        assert declaration in manifest

    assert '"SOUWEN_ADMIN_PASSWORD"' in manifest
    assert '"SOUWEN_CONFIG_B64"' in manifest
    assert '"UNIAPI_API_KEY"' in manifest
    assert 'workflow_owned_variables = ["SOUWEN_WRAPPER_SHA"]' in manifest
    assert "generic-sync-disabled" in manifest
    assert "workflow-owned-settings" in manifest


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
