"""Tests for the opt-in UniAPI Ark functional evidence script."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import uniapi_search_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import FetchResult, SearchCandidate, SearchSourceProvenance


SOURCE = "uniapi_ark_annotations_deepseek_v3_2_251201"


def _candidate() -> SearchCandidate:
    return SearchCandidate(
        title="Structured title",
        url="https://example.com/article",
        provenance=SearchSourceProvenance(
            source_id=SOURCE,
            scheme_id="uniapi_ark_annotations_v1",
            requested_model_id="deepseek-v3-2-251201",
            served_model_id="served-model",
        ),
    )


def test_verify_ark_source_contract_is_static_and_model_bound() -> None:
    _message, details = check.verify_ark_source_contract(SOURCE)

    assert details["source_id"] == SOURCE
    assert details["scheme_id"] == "uniapi_ark_annotations_v1"
    assert details["endpoint_type"] == "responses"
    assert details["runtime_default_enabled"] is False


def test_dry_run_writes_sanitized_report_without_live_execution(tmp_path: Path) -> None:
    json_report = tmp_path / "uniapi.json"
    markdown_report = tmp_path / "uniapi.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/uniapi_search_functional_check.py",
            "--source",
            SOURCE,
            "--mode",
            "dry-run",
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
    assert "SKIP live_execution" in completed.stdout
    report = json.loads(json_report.read_text(encoding="utf-8"))
    assert report["script"] == "uniapi_search_functional_check"
    assert report["mode"] == "dry-run"
    assert report["environment"]["live_execution_confirmed"] is False
    assert report["checks"][-1]["details"]["search_request_attempts"] == 0
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--source", SOURCE, "--mode", "live"]))


def test_sanitized_reports_omit_gateway_ids_and_opaque_content(tmp_path: Path) -> None:
    recorder = ResultRecorder(script="test", mode="live")
    recorder.record(
        "failure",
        Outcome.WARN,
        required=False,
        message=(
            "api_key=report-secret base_url=https://private.gateway.example/v1 "
            "response_id=response-secret"
        ),
        details={
            "api_key": "report-secret",
            "base_url": "https://private.gateway.example/v1",
            "response_id": "response-secret",
            "encrypted_content": "opaque-content",
            "safe": "kept",
        },
    )
    json_report = tmp_path / "safe.json"
    markdown_report = tmp_path / "safe.md"

    check._write_sanitized_reports(
        recorder, json_report=json_report, markdown_report=markdown_report
    )

    rendered = json_report.read_text(encoding="utf-8") + markdown_report.read_text(encoding="utf-8")
    assert "report-secret" not in rendered
    assert "private.gateway.example" not in rendered
    assert "response-secret" not in rendered
    assert "opaque-content" not in rendered
    assert '"safe": "kept"' in rendered


@pytest.mark.asyncio
async def test_live_smoke_makes_one_bound_search_then_one_bounded_fetch(monkeypatch):
    class FakeClient:
        search_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search_candidate_receipt(self, query: str, *, max_results: int):
            FakeClient.search_calls += 1
            assert query == "official query"
            assert max_results == 2
            return SimpleNamespace(
                candidates=(_candidate(),),
                visible_search_calls=1,
                provider_metered_search_calls=None,
                tool_call_types=("web_search_call",),
                valid_annotation_count=1,
                response_status="completed",
                input_tokens=12,
                output_tokens=6,
                total_tokens=18,
            )

    adapter = SimpleNamespace(client_loader=lambda: FakeClient)
    monkeypatch.setattr(check, "get_source_adapter", lambda source_id: adapter)
    fetch_calls: list[dict[str, object]] = []

    async def fake_fetch(urls, **kwargs):
        fetch_calls.append({"urls": urls, **kwargs})
        return SimpleNamespace(
            results=[
                FetchResult(
                    url=urls[0],
                    final_url=urls[0],
                    title="Fetched title",
                    content="Fetched body",
                    source="builtin",
                )
            ]
        )

    _message, details = await check.run_single_source_live_smoke(
        source_id=SOURCE,
        query="official query",
        max_results=2,
        fetch_provider="builtin",
        timeout=10,
        expected_url="https://example.com/article",
        fetcher=fake_fetch,
    )

    assert FakeClient.search_calls == 1
    assert len(fetch_calls) == 1
    assert details["search_request_attempts"] == 1
    assert details["automatic_model_fallback"] is False
    assert details["valid_annotation_count"] == 1
    assert details["fetched_title_present"] is True


@pytest.mark.asyncio
async def test_live_failure_is_warn_unless_required(monkeypatch):
    monkeypatch.setattr(check, "verify_ark_source_contract", lambda _source: ("ok", {}))
    monkeypatch.setattr(
        check,
        "run_single_source_live_smoke",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("gateway failure")),
    )
    recorder = ResultRecorder(script="test", mode="live")

    await check.run_selected_checks(
        argparse.Namespace(
            source=SOURCE,
            mode="live",
            required=False,
            timeout=1,
            query="q",
            max_results=1,
            fetch_provider="builtin",
            expected_url=None,
        ),
        recorder,
    )

    assert recorder.checks[-1].outcome == Outcome.WARN


@pytest.mark.asyncio
async def test_required_live_failure_remains_fail(monkeypatch):
    monkeypatch.setattr(check, "verify_ark_source_contract", lambda _source: ("ok", {}))
    monkeypatch.setattr(
        check,
        "run_single_source_live_smoke",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("gateway failure")),
    )
    recorder = ResultRecorder(script="test", mode="live")

    await check.run_selected_checks(
        argparse.Namespace(
            source=SOURCE,
            mode="live",
            required=True,
            timeout=1,
            query="q",
            max_results=1,
            fetch_provider="builtin",
            expected_url=None,
        ),
        recorder,
    )

    assert recorder.checks[-1].outcome == Outcome.FAIL
    assert recorder.exit_code() == 1
