"""tools/gen_docs.py 回归测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from tools import gen_docs


def test_cli_render_excludes_runtime_plugin_after_registry_import(clean_registry):
    from souwen.registry.adapter import MethodSpec, SourceAdapter
    from souwen.registry.loader import lazy
    from souwen.registry.views import _reg_external

    plugin_name = "gen_docs_runtime_probe"
    adapter = SourceAdapter(
        name=plugin_name,
        domain="fetch",
        integration="scraper",
        description="gen docs runtime probe",
        config_field=None,
        client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        needs_config=False,
    )

    assert _reg_external(adapter) is True
    assert plugin_name in gen_docs.render(include_plugins=True)
    assert plugin_name not in gen_docs.render_cli_content(include_plugins=False)


def test_checked_in_data_sources_matches_generator():
    docs_path = Path("docs/data-sources.md")
    rendered = gen_docs.render_cli_content(include_plugins=False)
    assert docs_path.read_text(encoding="utf-8") == rendered
    assert "静态 policy/config readiness" in rendered
    assert "Catalog 和 doctor 的 `runtime_available` / `runtime_reason`" in rendered
    assert "`available` 描述展示和运行时可用性" not in rendered


def test_registry_snapshot_drives_release_candidate_metrics():
    snapshot, _catalog, _categories = gen_docs._load_snapshot(include_plugins=False)

    assert snapshot.registered_count == 107
    assert snapshot.public_count == 106
    assert snapshot.hidden_or_internal_count == 1
    assert len(snapshot.fetch_primary) == 17
    assert [adapter.name for adapter in snapshot.fetch_cross_domain] == [
        "exa",
        "firecrawl",
        "kimi_code",
        "metaso",
        "tavily",
        "wayback",
        "xcrawl",
    ]
    assert snapshot.fetch_provider_count == 24


def test_checked_in_managed_regions_match_registry():
    managed = gen_docs.render_managed_files()

    assert set(managed) == {
        Path("README.md"),
        Path("README.en.md"),
        Path("docs/architecture.md"),
    }
    for relative_path, expected in managed.items():
        assert relative_path.read_text(encoding="utf-8") == expected


def test_check_flag_accepts_checked_in_data_sources():
    result = subprocess.run(
        [
            sys.executable,
            "tools/gen_docs.py",
            "--check",
        ],
        check=False,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, result.stderr
