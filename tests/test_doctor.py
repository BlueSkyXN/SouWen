from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from souwen.core.exceptions import ConfigError, RateLimitError
from souwen.doctor import (
    _live_probe_source,
    _source_names_filter,
    check_all_live,
    check_all,
    check_capabilities,
    format_report,
    summarize_live_probes,
    summarize_statuses,
)


def test_check_all_reports_runtime_and_configuration_axes() -> None:
    results = check_all()
    assert results
    required = {
        "name",
        "status",
        "enabled",
        "runtime_available",
        "runtime_reason",
        "credentials_satisfied",
        "config_available",
        "config_reason",
        "available",
    }
    assert required <= results[0].keys()


def test_capability_report_is_local_and_machine_readable() -> None:
    report = check_capabilities()
    assert "source_sha" in report
    assert {"sources", "fetch_providers", "package_extras", "llm_protocols", "warp_modes"} <= set(
        report["probe"]
    )


def test_report_and_summary_keep_runtime_statuses() -> None:
    results = check_all()
    summary = summarize_statuses(results)
    assert summary["total"] == len(results)
    assert "SouWen Doctor" in format_report(results)


@pytest.mark.parametrize(
    ("outcome", "expected_status", "message_fragment"),
    [
        (SimpleNamespace(error=None), "ok", "live search returned"),
        (SimpleNamespace(error="upstream failed"), "failed", "upstream failed"),
        (ConfigError("fixture_key", "Fixture"), "skipped", "missing config"),
        (RateLimitError("slow down"), "failed", "rate limited"),
        (asyncio.TimeoutError(), "failed", "timed out"),
        (RuntimeError("boom"), "failed", "RuntimeError: boom"),
    ],
)
async def test_live_probe_reports_elapsed_time(
    monkeypatch,
    outcome,
    expected_status,
    message_fragment,
) -> None:
    async def run_probe(*_args, **_kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    import souwen.doctor as doctor_module

    search_module = importlib.import_module("souwen.search")
    monkeypatch.setattr(
        doctor_module,
        "get_adapter",
        lambda _name: SimpleNamespace(capabilities={"search"}),
    )
    monkeypatch.setattr(search_module, "_run_via_adapter", run_probe)
    monkeypatch.setattr(
        doctor_module,
        "time",
        SimpleNamespace(monotonic=iter((10.0, 10.125)).__next__),
    )

    result = await _live_probe_source(
        {"name": "fixture", "enabled": True, "available": True, "status": "ok"},
        query="query",
        timeout=1.0,
    )

    assert result["status"] == expected_status
    assert message_fragment in result["message"]
    assert result["elapsed_ms"] == 125


@pytest.mark.parametrize(
    ("item", "adapter", "message"),
    [
        ({"enabled": False}, None, "source is disabled"),
        (
            {"enabled": True, "available": False, "status": "missing_key"},
            None,
            "static status is missing_key",
        ),
        (
            {"enabled": True, "available": True, "name": "fixture"},
            SimpleNamespace(capabilities={"fetch"}),
            "source does not expose search capability",
        ),
    ],
)
async def test_live_probe_skips_without_starting_network(
    monkeypatch, item, adapter, message
) -> None:
    import souwen.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "get_adapter", lambda _name: adapter)

    result = await _live_probe_source(item, query="query", timeout=1.0)

    assert result == {"status": "skipped", "message": message, "elapsed_ms": 0}


def test_live_probe_summary_and_source_filter() -> None:
    summary = summarize_live_probes(
        [
            {"live_probe": {"status": "ok"}},
            {"live_probe": {"status": "failed"}},
            {"live_probe": {"status": "skipped"}},
            {"name": "no-probe"},
        ]
    )

    assert summary["total"] == 3
    assert summary["status_counts"] == {"ok": 1, "failed": 1, "skipped": 1}
    assert _source_names_filter(None) is None
    assert _source_names_filter(" openalex ") == {"openalex"}
    assert _source_names_filter(["openalex", " ", "crossref"]) == {"openalex", "crossref"}


async def test_check_all_live_filters_and_attaches_probe(monkeypatch) -> None:
    import souwen.doctor as doctor_module

    results = [
        {"name": "openalex", "enabled": True, "available": True},
        {"name": "crossref", "enabled": True, "available": True},
    ]

    async def probe(item, *, query, timeout):
        return {"status": "ok", "message": f"{item['name']}:{query}", "elapsed_ms": int(timeout)}

    monkeypatch.setattr(doctor_module, "check_all", lambda: results)
    monkeypatch.setattr(doctor_module, "_live_probe_source", probe)

    output = await check_all_live(sources="openalex", query="fixture", timeout=0.1)

    assert output is results
    assert results[0]["live_probe"] == {
        "status": "ok",
        "message": "openalex:fixture",
        "elapsed_ms": 0,
    }
    assert "live_probe" not in results[1]
