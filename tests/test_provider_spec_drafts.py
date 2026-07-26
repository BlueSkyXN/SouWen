from __future__ import annotations

from tools import gen_provider_spec_drafts as drafts


def test_drafts_cover_only_pending_sources_without_inventing_mappings() -> None:
    data = drafts.build_drafts()

    assert data["schema_version"] == 1
    assert data["generator_version"] == drafts.GENERATOR_VERSION
    assert data["draft_count"] == 104
    assert data["existing_provider_spec_count"] == 6
    assert len(data["inventory_registry_sha256"]) == 64
    assert len(data["source_fingerprint"]["input_sha256"]) == 64
    assert all(
        draft[field] == {"review_required": True}
        for draft in data["drafts"]
        for field in ("request_mapping", "response_mapping", "error_mapping", "transport")
    )
    assert all(draft["migration_status"] == "pending" for draft in data["drafts"])
    assert all(
        draft[field] is None
        for draft in data["drafts"]
        for field in (
            "target_package",
            "target_manifest_id",
            "target_adapter_id",
            "target_capability",
            "target_spec_identity",
            "target_spec_path",
            "target_spec_reason",
        )
    )
    assert {spec["source_id"] for spec in data["existing_provider_specs"]} == {
        "builtin",
        "eric",
        "openalex",
        "patentsview",
        "uniapi_ark_annotations_deepseek_v3_2_251201",
        "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
    }
    assert all(
        spec["specification_status"] == "existing_provider_manifest"
        for spec in data["existing_provider_specs"]
    )
    assert next(
        spec for spec in data["existing_provider_specs"] if spec["source_id"] == "eric"
    ) == {
        "source_id": "eric",
        "provider_manifest_id": "eric",
        "target_package": "souwen.providers.information_sources.eric",
        "target_manifest_id": "eric",
        "target_adapter_id": "eric-search",
        "target_capability": "search",
        "target_spec_identity": "souwen.providers.information_sources.eric.spec.ERIC_REST_SPEC",
        "target_spec_path": "src/souwen/providers/information_sources/eric/spec.py",
        "target_spec_reason": None,
        "specification_status": "existing_provider_manifest",
    }
    assert all("fixture-secret" not in str(draft) for draft in data["drafts"])


def test_draft_check_mode_is_read_only_and_detects_drift(tmp_path) -> None:
    json_path = tmp_path / "drafts.json"
    markdown_path = tmp_path / "drafts.md"

    assert (
        drafts.main(
            ["--write", "--json-path", str(json_path), "--markdown-path", str(markdown_path)]
        )
        == 0
    )
    before = markdown_path.read_text(encoding="utf-8")
    assert (
        drafts.main(
            ["--check", "--json-path", str(json_path), "--markdown-path", str(markdown_path)]
        )
        == 0
    )
    assert markdown_path.read_text(encoding="utf-8") == before
    markdown_path.write_text("stale\n", encoding="utf-8")
    assert (
        drafts.main(
            ["--check", "--json-path", str(json_path), "--markdown-path", str(markdown_path)]
        )
        == 1
    )
