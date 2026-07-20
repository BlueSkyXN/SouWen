from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from tools.check_markdown_links import check_markdown_links


def test_markdown_link_checker_validates_paths_anchors_and_code_fences(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "target.md"
    target.write_text("# 标题 One\n\n## Duplicate\n\n## Duplicate\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text(
        "[valid](docs/target.md#标题-one)\n"
        "[duplicate](docs/target.md#duplicate-1)\n"
        "```md\n[ignored](missing.md)\n```\n",
        encoding="utf-8",
    )

    issues, count = check_markdown_links(tmp_path, [source, target])

    assert issues == []
    assert count == 2


def test_markdown_link_checker_reports_missing_path_and_anchor(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# Existing\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text(
        "[missing](missing.md)\n[anchor](target.md#absent)\n",
        encoding="utf-8",
    )

    issues, count = check_markdown_links(tmp_path, [source, target])

    assert count == 2
    assert [issue.reason for issue in issues] == [
        "local path does not exist with exact case",
        "Markdown anchor not found: #absent",
    ]


def test_markdown_link_cli_writes_machine_readable_report(tmp_path: Path) -> None:
    report = tmp_path / "links.json"
    result = subprocess.run(
        [sys.executable, "tools/check_markdown_links.py", "--json-report", str(report)],
        check=False,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["overall"] == "PASS"
    assert payload["file_count"] >= 1
    assert payload["issues"] == []
