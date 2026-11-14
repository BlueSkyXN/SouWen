"""Deterministic coverage for ``souwen doctor --live`` per-level probes.

The pinned planner must implement the full planner surface BaseScraper calls
(effective_bounds before plan), transport verdicts must record the level that
actually executed, and program errors must be separated from upstream
failures (a planner interface break previously collapsed every source into
FAIL/invalid_upstream_response).
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from souwen.common_runtime.egress.levels import EgressBounds, EgressLevel
from souwen.server import doctor
from souwen.server.doctor import (
    LevelVerdict,
    LiveReport,
    _PinnedPlanner,
    run_live_census,
)


class TestPinnedPlannerInterface:
    def test_effective_bounds_exists_and_clamps_to_source_bounds(self):
        planner = _PinnedPlanner("browser", lambda: None)
        effective = planner.effective_bounds(EgressBounds())
        assert effective.min_level is EgressLevel.PROXY
        assert effective.max_level is EgressLevel.PROXY

    def test_plan_reports_pinned_level_within_source_bounds(self):
        planner = _PinnedPlanner("browser", lambda: "socks5://localhost:14000")
        browser_bounds = EgressBounds(
            min_level=EgressLevel.IMPERSONATE, max_level=EgressLevel.BROWSER
        )
        decision = planner.plan("html.duckduckgo.org", browser_bounds)
        assert decision.level is EgressLevel.BROWSER
        assert decision.proxy is None  # proxy only applies to the proxy level

    def test_plan_proxy_level_carries_proxy(self):
        planner = _PinnedPlanner("proxy", lambda: "socks5://localhost:14000")
        decision = planner.plan("search.yahoo.com", EgressBounds())
        assert decision.level is EgressLevel.PROXY
        assert decision.proxy == "socks5://localhost:14000"

    def test_plan_records_planned_host(self):
        planner = _PinnedPlanner("direct", lambda: None)
        planner.plan("Search.Yahoo.COM", EgressBounds())
        assert "search.yahoo.com" in planner.planned_hosts

    def test_report_hooks_exist(self):
        planner = _PinnedPlanner("direct", lambda: None)
        planner.report_success("h", EgressLevel.DIRECT)
        planner.report_failure("h", EgressLevel.DIRECT)


class _RecordingSearchService:
    """Fake search service that records the transport egress per source."""

    def __init__(self, sources: dict[str, str]) -> None:
        # source id -> transport outcome: "browser" | "proxy" | "upstream_fail"
        self._sources = sources
        self.planned_hosts: set[str] = set()

    async def search(self, request, context, execution):
        provider = request.providers[0].id
        outcome = self._sources[provider]
        if outcome == "upstream_fail":
            from souwen.platform.provider_spi import ProviderError

            raise ProviderError(doctor.ProviderErrorCode.INVALID_UPSTREAM_RESPONSE)
        if outcome == "program_error":
            raise AttributeError("_PinnedPlanner object has no attribute")
        page = _fake_page(provider)
        self.planned_hosts.add(provider)
        return page


class _FakeProviderItem:
    def __init__(self, provider: str, domain: str, capability: str = "search") -> None:
        self.provider = provider
        self.domain = domain
        self.capabilities = (capability,)
        self.availability = "available"


class _FakeFetchService:
    def __init__(self, outcome: str = "ok") -> None:
        self._outcome = outcome
        self.targets: list[str] = []

    async def fetch(self, request, context, execution):
        from souwen.platform.provider_spi import (
            ContentMetadata,
            ErrorDetail,
            FetchBatch,
            FetchMeta,
            FetchResult,
            Provenance,
        )

        self.targets.append(str(request.targets[0]))
        target = str(request.targets[0])
        if self._outcome == "ok":
            item = FetchResult(
                target=target,
                final_url=target,
                status="success",
                title="T",
                content="body " * 80,
                content_metadata=ContentMetadata(
                    media_type="text/html",
                    retrieved_at=None,
                    truncated=False,
                    quality="high",
                    egress="browser",
                ),
                provenance=(Provenance(provider="builtin-fetch", outcome="success"),),
            )
        else:
            item = FetchResult(
                target=target,
                final_url=None,
                status="failed",
                error=ErrorDetail(
                    code="provider_unavailable",
                    message="unavailable",
                    retryable=True,
                    request_id="t",
                    provider="builtin-fetch",
                ),
                provenance=(Provenance(provider="builtin-fetch", outcome="failed"),),
            )
        return FetchBatch(items=(item,), meta=FetchMeta(), context=context)


class _FakeServices:
    def __init__(self, service, items, fetch_service=None) -> None:
        self.search = service
        self.provider_items = tuple(items)
        self.fetch = fetch_service or _FakeFetchService()


class _FakeRuntime:
    def __init__(self, services) -> None:
        self.services = services

    async def close(self) -> None:
        return None


def _fake_page(provider: str):
    from souwen.platform.provider_spi import (
        PageInfo,
        Provenance,
        RequestContext,
        SearchItem,
        SearchMeta,
        SearchPage,
    )

    items = tuple(
        SearchItem(
            id=f"{provider}:{rank}",
            title=f"result {rank}",
            url=f"https://example.com/{provider}/{rank}",
            rank=rank,
            provenance=(Provenance(provider=provider, attempt=1, outcome="success"),),
        )
        for rank in range(1, 4)
    )
    return SearchPage(
        items=items,
        page=PageInfo(limit=5, total=len(items)),
        meta=SearchMeta(requested=(provider,), succeeded=(provider,)),
        context=RequestContext(request_id=f"doctor-test-{provider}"),
    )


@pytest.fixture()
def live_census_env(monkeypatch, tmp_path):
    queries = {
        "domains": {
            "web": ["q1", "q2", "q3"],
            "news": ["q1", "q2", "q3"],
        },
        "fetch_urls": {
            "static": ["https://example.com/static"],
            "js": ["https://example.com/js"],
            "anticrawl": ["https://example.com/anticrawl"],
        },
    }
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(__import__("json").dumps(queries), encoding="utf-8")
    monkeypatch.setenv("SOUWEN_CENSUS_QUERIES", str(queries_path))

    def fake_build(_config):
        sources = {
            # host 对应 doctor 里 search_source_hosts 的键（源 id → 主机）
            "brave": "browser",
            "yahoo": "proxy",
            "baidu": "upstream_fail",
            "duckduckgo_news": "program_error",
        }
        service = _RecordingSearchService(sources)
        items = [
            _FakeProviderItem("brave", "web"),
            _FakeProviderItem("yahoo", "web"),
            _FakeProviderItem("baidu", "web"),
            _FakeProviderItem("duckduckgo_news", "news"),
        ]
        return _FakeRuntime(_FakeServices(service, items))

    monkeypatch.setattr(doctor, "build_target_runtime", fake_build)
    import souwen.server.v2_runtime as v2_runtime_module

    hosts = {
        "brave": "search.brave.com",
        "yahoo": "search.yahoo.com",
        "baidu": "www.baidu.com",
        "duckduckgo_news": "duckduckgo.com",
    }
    monkeypatch.setattr(v2_runtime_module, "search_source_hosts", lambda: hosts)
    monkeypatch.setattr(
        v2_runtime_module, "search_domains_by_provider", lambda: {"duckduckgo_news": "news"}
    )

    async def fake_close_pools():
        return None

    monkeypatch.setattr(
        "souwen.common_runtime.provider_support.browser_fetch.close_shared_pools",
        fake_close_pools,
    )
    return queries_path


def test_run_live_census_records_used_level_and_separates_program_errors(
    live_census_env, monkeypatch
):
    monkeypatch.setattr(doctor.SouWenConfig, "get_proxy", lambda self: None, raising=False)
    # planner_module._planner 在 run_live_census 内部赋值；这里只需结果正确
    reports = run_live_census(["browser", "proxy"])
    by_source = {
        (report.level, verdict.source): verdict for report in reports for verdict in report.verdicts
    }
    # 走到传输层的源记录 used_level；本测试的 fake service 不经 BaseScraper，
    # planned_hosts 为空 → used_level 仍是 None，但程序错误必须显式成 ERROR。
    program = by_source[("browser", "duckduckgo_news")]
    assert program.outcome == "ERROR"
    assert program.program_error and "AttributeError" in program.program_error

    upstream = by_source[("browser", "baidu")]
    assert upstream.outcome == "FAIL"
    assert upstream.program_error is None

    ok = by_source[("browser", "brave")]
    assert ok.outcome == "PASS"

    # 两个级别都产出了报告，JSON 导出路径可用（asdict 覆盖新字段）
    payload = [dataclasses.asdict(v) for r in reports for v in r.verdicts]
    assert any(item["program_error"] for item in payload)


def test_print_live_reports_handles_error_outcome(live_census_env, capsys):
    report = LiveReport(
        level="browser",
        started_at="2026-11-14T00:00:00Z",
        duration_seconds=1.0,
        verdicts=[
            LevelVerdict(
                source="x",
                level="browser",
                outcome="ERROR",
                valid_count=0,
                total=3,
                detail="",
                program_error="TypeError: boom",
            )
        ],
    )
    doctor.print_live_reports([report])
    out = capsys.readouterr().out
    assert "ERROR" in out or "TypeError: boom" in out


def test_probe_source_upstream_provider_error_records_detail(live_census_env):
    async def scenario():
        service = _RecordingSearchService({"baidu": "upstream_fail"})
        runtime = _FakeRuntime(_FakeServices(service, [_FakeProviderItem("baidu", "web")]))
        return await doctor._probe_source(runtime, "baidu", ["q1", "q2", "q3"])

    verdict = asyncio.run(scenario())
    assert verdict.outcome == "FAIL"
    assert verdict.program_error is None


def test_fetch_probes_cover_all_three_url_classes(live_census_env, monkeypatch):
    """doctor --live 的 fetch 探测覆盖 static/js/anticrawl 三类（每类首个）。"""

    import souwen.server.v2_runtime as v2_runtime_module

    from souwen.platform.provider_spi import (
        PageInfo,
        Provenance,
        RequestContext,
        SearchItem,
        SearchMeta,
        SearchPage,
    )

    def fake_page(provider: str) -> SearchPage:
        items = tuple(
            SearchItem(
                id=f"{provider}:{rank}",
                title=f"result {rank}",
                url=f"https://example.com/{provider}/{rank}",
                rank=rank,
                provenance=(Provenance(provider=provider, attempt=1, outcome="success"),),
            )
            for rank in range(1, 4)
        )
        return SearchPage(
            items=items,
            page=PageInfo(limit=5, total=len(items)),
            meta=SearchMeta(requested=(provider,), succeeded=(provider,)),
            context=RequestContext(request_id=f"doctor-test-{provider}"),
        )

    class _Search:
        async def search(self, request, context, execution):
            return fake_page(request.providers[0].id)

    fetch_service = _FakeFetchService()
    runtime = _FakeRuntime(_FakeServices(_Search(), [], fetch_service=fetch_service))
    monkeypatch.setattr(doctor, "build_target_runtime", lambda cfg: runtime)
    monkeypatch.setattr(v2_runtime_module, "search_source_hosts", lambda: {})

    reports = doctor.run_live_census(["browser"])
    fetch_verdicts = [v for v in reports[0].verdicts if v.source.startswith("fetch:")]
    assert len(fetch_verdicts) == 3
    assert all(v.outcome == "PASS" for v in fetch_verdicts)
    assert {v.source for v in fetch_verdicts} == {
        "fetch:https://example.com/static",
        "fetch:https://example.com/js",
        "fetch:https://example.com/anticrawl",
    }
    # fetch 探测的 used_level 反映 ContentMetadata.egress
    assert all(v.used_level == "browser" for v in fetch_verdicts)
    assert fetch_service.targets == [
        "https://example.com/static",
        "https://example.com/js",
        "https://example.com/anticrawl",
    ]
