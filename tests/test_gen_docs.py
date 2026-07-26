"""tools/gen_docs.py 回归测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from tools import gen_docs


def test_checked_in_data_sources_matches_generator():
    docs_path = Path("docs/data-sources.md")
    rendered = gen_docs.render_cli_content()
    assert docs_path.read_text(encoding="utf-8") == rendered
    assert "Manifest Registry 与 Provider Manager 是唯一运行时事实来源" in rendered
    assert "公开能力严格只有 `search`、`llm_search`、`fetch`" in rendered
    assert "opencitations" not in rendered


def test_manifest_snapshot_drives_release_candidate_metrics():
    snapshot = gen_docs._load_snapshot()

    assert snapshot.package_count == 104
    assert snapshot.adapter_count == 110
    assert snapshot.capability_count("search") == 88
    assert snapshot.capability_count("llm_search") == 2
    assert snapshot.capability_count("fetch") == 20
    assert [manifest.id for manifest in snapshot.multi_capability] == [
        "exa",
        "firecrawl",
        "kimi_code",
        "metaso",
        "tavily",
        "xcrawl",
    ]


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
