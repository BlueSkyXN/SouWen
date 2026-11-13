"""``souwen doctor --live``: per-egress-level source census in-process (SPEC 6.1).

Reuses the frozen census queries (scripts/census/queries.json) and the
PASS/WARN/FAIL verdict semantics, but executes through the module services
directly with the egress planner pinned to one level, so every source gets
a result at every level without going through HTTP.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from souwen.config import SouWenConfig, get_config
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.server.v2_runtime import TargetRuntime, build_target_runtime

_QUERIES_CANDIDATES = (
    Path("scripts/census/queries.json"),
    Path("/app/scripts/census/queries.json"),
)
_PROBES_PER_SOURCE = 3
_MIN_VALID_RESULTS = 3


@dataclass(slots=True)
class LevelVerdict:
    source: str
    level: str
    outcome: str
    valid_count: int
    total: int
    detail: str = ""
    # 实际作用到传输的级别；None = 该源的客户端不经出口阶梯（如纯 API 客户端）
    used_level: str | None = None


@dataclass(slots=True)
class LiveReport:
    level: str
    started_at: str
    duration_seconds: float
    verdicts: list[LevelVerdict] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for verdict in self.verdicts:
            counts[verdict.outcome] = counts.get(verdict.outcome, 0) + 1
        return counts


class _PinnedPlanner:
    """Planner that always answers with one fixed level (doctor --live).

    记录请求过 plan 的主机：源声明的传输主机若从未出现，说明其客户端
    不走出口阶梯，verdict 如实标注 used_level=None。
    """

    def __init__(self, level_name: str, proxy_provider) -> None:
        self.level_name = level_name
        self._proxy_provider = proxy_provider
        self.planned_hosts: set[str] = set()

    def plan(self, host: str, bounds):
        from souwen.common_runtime.egress.levels import parse_egress_level

        self.planned_hosts.add((host or "").lower().lstrip("."))
        level = parse_egress_level(self.level_name)
        proxy = self._proxy_provider() if level.label == "proxy" else None
        return _Decision(level, proxy, "doctor-pinned")

    def report_success(self, host, level) -> None:
        return None

    def report_failure(self, host, level) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _Decision:
    level: object
    proxy: str | None
    reason: str


def _load_queries() -> dict:
    import os

    override = Path(os.environ.get("SOUWEN_CENSUS_QUERIES", ""))
    for candidate in (override, *_QUERIES_CANDIDATES):
        if candidate and candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "frozen census queries not found; run from the repo or set SOUWEN_CENSUS_QUERIES"
    )


def _verdict(valid: int, total: int) -> str:
    if total <= 0:
        return "SKIP"
    if valid >= 2:
        return "PASS"
    if valid == 1:
        return "WARN"
    return "FAIL"


def _item_valid(item) -> bool:
    url = str(item.url) if getattr(item, "url", None) is not None else ""
    title = (getattr(item, "title", "") or "").strip()
    return bool(title) and url.startswith(("http://", "https://"))


async def _probe_source(runtime: TargetRuntime, source: str, queries: list[str]) -> LevelVerdict:
    valid = 0
    detail = ""
    for query in queries[:_PROBES_PER_SOURCE]:
        request = SearchRequest(
            query=query,
            domains=(_domain_for(runtime, source),),
            providers=(ProviderRef(id=source, kind="search"),),
            page=SearchPageRequest(limit=5),
        )
        try:
            page = await runtime.services.search.search(
                request,
                RequestContext(request_id=f"doctor-{source}"),
                ExecutionContext.with_timeout(30),
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            detail = str(getattr(code, "value", type(exc).__name__))
            continue
        if sum(1 for item in page.items if _item_valid(item)) >= _MIN_VALID_RESULTS:
            valid += 1
        elif not detail:
            detail = f"only {len(page.items)} items"
    return LevelVerdict(
        source=source,
        level="",
        outcome=_verdict(valid, _PROBES_PER_SOURCE),
        valid_count=valid,
        total=_PROBES_PER_SOURCE,
        detail=detail,
    )


def _domain_for(runtime: TargetRuntime, source: str) -> str:
    for item in runtime.services.provider_items:
        if item.provider == source:
            domain = getattr(item, "domain", None)
            if domain:
                return domain
    from souwen.server.v2_runtime import search_domains_by_provider

    return search_domains_by_provider().get(source, "web")


def run_live_census(levels: list[str], *, only: set[str] | None = None) -> list[LiveReport]:
    """Run the frozen per-source probes at each pinned egress level."""

    queries = _load_queries()
    config: SouWenConfig = get_config()
    proxy_provider = lambda: config.get_proxy() or None  # noqa: E731

    reports: list[LiveReport] = []
    for level in levels:
        from souwen.common_runtime.egress import planner as planner_module

        planner_module._planner = _PinnedPlanner(level, proxy_provider)
        runtime = build_target_runtime(SouWenConfig())
        started = time.time()
        report = LiveReport(
            level=level,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            duration_seconds=0.0,
        )
        from souwen.server.v2_runtime import search_source_hosts

        source_hosts = search_source_hosts()
        catalog = {item.provider: item for item in runtime.services.provider_items}
        sources = [
            item.provider
            for item in runtime.services.provider_items
            if item.capabilities[0] == "search" and item.availability == "available"
        ]
        if only:
            sources = [source for source in sources if source in only]
        unavailable = [
            item.provider
            for item in runtime.services.provider_items
            if item.capabilities[0] == "search" and item.availability != "available"
        ]
        if only:
            unavailable = [source for source in unavailable if source in only]

        async def run_all():
            # 探测与 close 必须在同一个事件循环里（httpx 客户端不能跨 loop 关闭）
            verdicts = await asyncio.gather(
                *(
                    _probe_source(
                        runtime,
                        source,
                        queries["domains"][_domain_for(runtime, source)],
                    )
                    for source in sources
                )
            )
            try:
                await runtime.close()
            except Exception:
                pass
            try:
                from souwen.common_runtime.provider_support.browser_fetch import (
                    close_shared_pools,
                )

                await close_shared_pools()
            except Exception:
                pass
            return verdicts

        verdicts = asyncio.run(run_all())
        planned = planner_module._planner.planned_hosts
        for verdict in verdicts:
            verdict.level = level
            host = (source_hosts.get(verdict.source) or "").lower().lstrip(".")
            if host and host in planned:
                verdict.used_level = level
            else:
                verdict.detail = (verdict.detail + "; " if verdict.detail else "") + (
                    "client bypasses egress ladder (pin not applied)"
                )
        for source in unavailable:
            reason = getattr(catalog.get(source), "reason", None)
            verdicts.append(
                LevelVerdict(
                    source=source,
                    level=level,
                    outcome="SKIP",
                    valid_count=0,
                    total=0,
                    detail=f"unavailable ({reason or 'unknown'})",
                    used_level=None,
                )
            )
        report.verdicts = list(verdicts)
        report.duration_seconds = round(time.time() - started, 1)
        reports.append(report)
    return reports


def print_live_reports(reports: list[LiveReport], *, json_file: str | None = None) -> None:
    for report in reports:
        counts = report.counts
        print(
            f"\n== egress level {report.level} ({report.duration_seconds}s) "
            f"PASS={counts.get('PASS', 0)} WARN={counts.get('WARN', 0)} FAIL={counts.get('FAIL', 0)} =="
        )
        for verdict in sorted(report.verdicts, key=lambda v: (v.outcome != "PASS", v.source)):
            marker = {"PASS": "+", "WARN": "~", "FAIL": "x", "SKIP": "-"}.get(verdict.outcome, "?")
            used = verdict.used_level or "no-ladder"
            print(
                f"  [{marker}] {verdict.source:22} {verdict.valid_count}/{verdict.total} "
                f"used={used:11} {verdict.detail}"
            )
    if json_file:
        payload = [
            {
                "level": report.level,
                "started_at": report.started_at,
                "duration_seconds": report.duration_seconds,
                "verdicts": [dataclasses.asdict(verdict) for verdict in report.verdicts],
            }
            for report in reports
        ]
        Path(json_file).parent.mkdir(parents=True, exist_ok=True)
        Path(json_file).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nreport written to {json_file}", file=sys.stderr)


__all__ = ["LiveReport", "LevelVerdict", "print_live_reports", "run_live_census"]
