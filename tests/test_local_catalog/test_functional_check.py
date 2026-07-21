from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import local_catalog_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.local_catalog.gutenberg import LIVE_SAMPLE_RDF_URL, DownloadReceipt


_RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:pgterms="http://www.gutenberg.org/2009/pgterms/" xml:base="https://www.gutenberg.org/">
  <pgterms:ebook rdf:about="ebooks/11">
    <dcterms:title>Alice's Adventures in Wonderland</dcterms:title>
    <dcterms:creator><pgterms:agent><pgterms:name>Carroll, Lewis</pgterms:name></pgterms:agent></dcterms:creator>
    <dcterms:rights>Public domain in the USA.</dcterms:rights>
    <dcterms:hasFormat><pgterms:file rdf:about="https://www.gutenberg.org/ebooks/11.epub3.images" /></dcterms:hasFormat>
  </pgterms:ebook>
</rdf:RDF>"""


def test_verify_gutenberg_registered_reports_explicit_local_catalog_contract() -> None:
    message, details = check.verify_gutenberg_registered()

    assert message == "gutenberg registry contract passed"
    assert details == {
        "source": "gutenberg",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
        "access_mode": "local_catalog_metadata_only",
    }


def test_bounded_live_smoke_downloads_only_pg11_rdf_and_uses_temporary_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_download(url: str, destination: Path) -> DownloadReceipt:
        calls.append(url)
        destination.write_bytes(_RDF)
        return DownloadReceipt(
            path=destination,
            url=url,
            content_length=len(_RDF),
            last_modified=None,
            sha256=hashlib.sha256(_RDF).hexdigest(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    monkeypatch.setattr(
        "souwen.local_catalog.gutenberg.download_official_gutenberg_catalog", fake_download
    )

    message, details = check.run_gutenberg_local_catalog_smoke()

    assert message == "Gutenberg local catalog imported and queried record 11"
    assert calls == [LIVE_SAMPLE_RDF_URL]
    assert details["sample_url"] == LIVE_SAMPLE_RDF_URL
    assert details["sample_id"] == "11"
    assert details["second_import"]["unchanged"] == 1
    assert details["integrity"] == "ok"
    assert details["database_is_temporary"] is True
    assert details["no_ebook_or_declared_resource_url_fetch"] is True


def test_offline_mode_writes_skip_reports_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "local-catalog.json"
    markdown_report = tmp_path / "local-catalog.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/local_catalog_functional_check.py",
            "--mode",
            "offline",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "SKIP offline_mode" in completed.stdout
    report = json.loads(json_report.read_text(encoding="utf-8"))
    assert report["script"] == "local_catalog_functional_check"
    assert report["overall"] == "SKIP"
    assert report["environment"]["contract"] == "official_project_gutenberg_rdf_xml_local_catalog"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required", "expected_outcome", "expected_exit_code"),
    [(False, Outcome.WARN, 0), (True, Outcome.FAIL, 1)],
)
async def test_live_failures_are_warn_only_unless_required(
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
    expected_outcome: Outcome,
    expected_exit_code: int,
) -> None:
    def failing_live_check() -> tuple[str, dict[str, object]]:
        raise RuntimeError("official endpoint unavailable")

    monkeypatch.setattr(check, "verify_gutenberg_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_gutenberg_local_catalog_smoke", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(mode="live", required=required, timeout=1.0)

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
