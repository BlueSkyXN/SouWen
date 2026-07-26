from __future__ import annotations

import json

from tools import provider_migration_inventory as inventory


def test_inventory_partitions_the_current_registry_into_six_batches() -> None:
    data = inventory.build_inventory()

    assert data["schema_version"] == 1
    assert data["generator_version"] == inventory.GENERATOR_VERSION
    assert data["registry_count"] == 110
    assert data["batch_counts"] == {
        "sample": 6,
        "batch-1": 14,
        "batch-2": 14,
        "batch-3": 33,
        "batch-4": 11,
        "batch-5": 29,
        "batch-6": 3,
        "unclassified": 0,
    }
    assert data["batch_counts"] == inventory.EXPECTED_COUNTS
    assert data["status_counts"] == {"migrated": 6, "pending": 104, "incomplete": 0}
    assert len(data["records"]) == 110
    assert len({record["source_id"] for record in data["records"]}) == len(data["records"])
    assert data["classification_complete"] is True
    assert all(
        record["batch"] in {inventory.SAMPLE_BATCH, *inventory.BATCH_ORDER}
        for record in data["records"]
    )
    assert set(data["source_fingerprint"]) == {
        "registry_metadata_sha256",
        "provider_manifest_ids_sha256",
        "input_sha256",
    }
    assert all(len(value) == 64 for value in data["source_fingerprint"].values())
    exceptions = [
        record
        for record in data["records"]
        if record["classification_reason"]
        == "paper full-text companion source; migrate with paper/patent no-key batch"
    ]
    assert [(record["source_id"], record["batch"]) for record in exceptions] == [
        ("arxiv_fulltext", "batch-1")
    ]
    assert {
        record["source_id"]
        for record in data["records"]
        if record["migration_status"] == "migrated"
    } == inventory.SAMPLE_SOURCE_IDS
    assert all(
        record["migration_status"] == "pending"
        for record in data["records"]
        if record["batch"] != inventory.SAMPLE_BATCH
    )


def test_inventory_is_value_free_and_matches_existing_manifest_identities() -> None:
    data = inventory.build_inventory()
    records = {record["source_id"]: record for record in data["records"]}

    assert {
        name for name, record in records.items() if record["migration_status"] == "migrated"
    } == {
        "builtin",
        "eric",
        "openalex",
        "patentsview",
        "uniapi_ark_annotations_deepseek_v3_2_251201",
        "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
    }
    assert records["builtin"]["provider_manifest_id"] == "builtin-fetch"
    assert records["eric"] == {
        **records["eric"],
        "target_package": "souwen.providers.information_sources.eric",
        "target_manifest_id": "eric",
        "target_adapter_id": "eric-search",
        "target_capability": "search",
        "target_spec_identity": "souwen.providers.information_sources.eric.spec.ERIC_REST_SPEC",
        "target_spec_path": "src/souwen/providers/information_sources/eric/spec.py",
        "target_spec_reason": None,
    }
    assert records["builtin"]["target_spec_identity"] is None
    assert records["builtin"]["target_spec_path"] is None
    assert records["builtin"]["target_spec_reason"] == (
        "capability-specific Fetch Provider is covered by deterministic conformance"
    )
    assert all(
        record[field] is None
        for record in data["records"]
        if record["migration_status"] == "pending"
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
    assert all("secret" not in key.lower() for record in data["records"] for key in record)
    assert "fixture-secret" not in inventory.render_json(data)


def test_a_future_manifest_without_a_reviewed_spec_fails_closed_and_preserves_batch(
    monkeypatch,
) -> None:
    targets = inventory._manifest_targets()
    targets["arxiv"] = {
        "package": "souwen.providers.information_sources.arxiv",
        "manifest_path": "src/souwen/providers/information_sources/arxiv/manifest.py",
        "adapters": [{"adapter_id": "arxiv-search", "capability": "search"}],
    }
    monkeypatch.setattr(inventory, "_manifest_targets", lambda: targets)

    data = inventory.build_inventory()
    record = next(record for record in data["records"] if record["source_id"] == "arxiv")

    assert record["batch"] == "batch-1"
    assert record["migration_status"] == "incomplete"
    assert data["classification_complete"] is False


def test_manifest_ids_are_limited_to_static_provider_manifest_identities() -> None:
    assert inventory._manifest_ids() == {
        "builtin-fetch",
        "eric",
        "openalex",
        "patentsview",
        "uniapi_ark_annotations_deepseek_v3_2_251201",
        "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
    }


def test_inventory_check_mode_is_read_only_and_detects_drift(tmp_path) -> None:
    json_path = tmp_path / "inventory.json"
    markdown_path = tmp_path / "inventory.md"

    assert (
        inventory.main(
            ["--write", "--json-path", str(json_path), "--markdown-path", str(markdown_path)]
        )
        == 0
    )
    before = json_path.read_text(encoding="utf-8")
    assert (
        inventory.main(
            [
                "--check",
                "--require-complete",
                "--json-path",
                str(json_path),
                "--markdown-path",
                str(markdown_path),
            ]
        )
        == 0
    )
    assert json_path.read_text(encoding="utf-8") == before
    json_path.write_text(json.dumps({"stale": True}) + "\n", encoding="utf-8")
    assert (
        inventory.main(
            ["--check", "--json-path", str(json_path), "--markdown-path", str(markdown_path)]
        )
        == 1
    )
