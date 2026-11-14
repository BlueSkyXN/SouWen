"""Deterministic tests for the fetch ladder: handlers, last resorts, chain."""

from __future__ import annotations

import asyncio

import pytest

from souwen.modules.fetch.application.orchestration import (
    FetchModuleService,
    SiteHandler,
)
from souwen.platform.provider_spi import (
    ContentMetadata,
    ProviderErrorCode,
    Provenance,
    ErrorDetail,
    ExecutionContext,
    FetchRequest,
    FetchResult,
    ProviderError,
    RequestContext,
)


def _result(url, *, provider="builtin-fetch", status="success", content="word " * 120):
    error = None
    if status != "success":
        error = ErrorDetail(
            code="provider_unavailable",
            message="unavailable",
            retryable=True,
            request_id="t",
            provider=provider,
        )
    return FetchResult(
        target=url,
        final_url=url if status == "success" else None,
        status=status,
        title="T" if status == "success" else None,
        content=content if status == "success" else None,
        content_metadata=(
            ContentMetadata(media_type="text/markdown", truncated=False, quality="high")
            if status == "success"
            else None
        ),
        provenance=(
            Provenance(provider=provider, outcome="success" if status == "success" else "failed"),
        ),
        error=error,
    )


class _Manager:
    def __init__(self, behavior: dict[str, str]) -> None:
        self.behavior = behavior
        self.calls: list[str] = []

    async def execute(self, adapter_id, request, request_context, execution):
        self.calls.append(adapter_id)
        outcome = self.behavior.get(adapter_id)
        if outcome == "raise":
            raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
        return _result(
            str(request.target),
            provider=adapter_id,
            status="success" if outcome == "ok" else "failed",
        )


def _service(behavior, *, jina=False):
    last_resort = [("wayback", "wayback-fetch")]
    if jina:
        last_resort.append(("jina_reader", "jina-reader-fetch"))
    manager = _Manager(behavior)
    service = FetchModuleService(
        manager,
        site_handlers=(
            SiteHandler(
                provider_id="arxiv_fulltext",
                adapter_id="arxiv_fulltext-fetch",
                matches=lambda url: "arxiv.org" in url,
            ),
        ),
        last_resort_providers=tuple(last_resort),
    )
    return service, manager


def _run(service, url):
    return asyncio.run(
        service.fetch(
            FetchRequest(targets=(url,)),
            RequestContext(request_id="ladder"),
            ExecutionContext.with_timeout(10),
        )
    )


def test_arxiv_url_runs_site_handler_first() -> None:
    service, manager = _service({"arxiv_fulltext-fetch": "ok", "builtin-fetch": "ok"})

    batch = _run(service, "https://arxiv.org/abs/1706.03762")

    assert manager.calls == ["arxiv_fulltext-fetch"]
    assert batch.items[0].status == "success"


def test_non_arxiv_url_skips_site_handler() -> None:
    service, manager = _service({"builtin-fetch": "ok"})

    _run(service, "https://example.com/article")

    assert manager.calls == ["builtin-fetch"]


def test_site_handler_rejection_falls_through_to_builtin() -> None:
    service, manager = _service({"arxiv_fulltext-fetch": "raise", "builtin-fetch": "ok"})

    batch = _run(service, "https://arxiv.org/abs/9999.9999")

    assert manager.calls == ["arxiv_fulltext-fetch", "builtin-fetch"]
    assert batch.items[0].status == "success"


def test_wayback_runs_only_when_builtin_fails() -> None:
    service, manager = _service({"builtin-fetch": "ok", "wayback-fetch": "ok"})

    _run(service, "https://example.com/down")

    assert manager.calls == ["builtin-fetch"]


def test_wayback_rescues_unreachable_page() -> None:
    service, manager = _service({"builtin-fetch": "failed", "wayback-fetch": "ok"})

    batch = _run(service, "https://example.com/down")

    assert manager.calls == ["builtin-fetch", "wayback-fetch"]
    assert batch.items[0].status == "success"


def test_jina_participates_only_when_enabled() -> None:
    service_off, manager_off = _service(
        {"builtin-fetch": "failed", "wayback-fetch": "failed", "jina-reader-fetch": "ok"}
    )
    with pytest.raises(ProviderError):
        _run(service_off, "https://example.com/x")
    assert "jina-reader-fetch" not in manager_off.calls

    service_on, manager_on = _service(
        {"builtin-fetch": "failed", "wayback-fetch": "failed", "jina-reader-fetch": "ok"},
        jina=True,
    )
    batch = _run(service_on, "https://example.com/x")
    assert manager_on.calls == ["builtin-fetch", "wayback-fetch", "jina-reader-fetch"]
    assert batch.items[0].status == "success"


def test_low_quality_builtin_skips_last_resort() -> None:
    manager = _Manager({"builtin-fetch": "ok"})

    async def low_quality_target():
        # 让 builtin 返回低质量正文：quality=low
        result = _result("https://example.com/short", content="word " * 120)
        result = result.model_copy(
            update={
                "content": "tiny",
                "content_metadata": ContentMetadata(
                    media_type="text/markdown", truncated=False, quality="low", content_length=4
                ),
            }
        )

        async def execute(adapter_id, request, request_context, execution):
            manager.calls.append(adapter_id)
            return result

        manager.execute = execute  # type: ignore[method-assign]
        service = FetchModuleService(
            manager,
            last_resort_providers=(("wayback", "wayback-fetch"),),
        )
        return await service.fetch(
            FetchRequest(targets=("https://example.com/short",)),
            RequestContext(request_id="lowq"),
            ExecutionContext.with_timeout(10),
        )

    batch = asyncio.run(low_quality_target())
    assert manager.calls == ["builtin-fetch"]
    assert batch.items[0].status == "success"


def test_extractor_chain_prefers_first_sufficient_result(monkeypatch) -> None:
    from souwen.providers.runtime_clients.web import _extractor_chain as chain

    order: list[str] = []

    def traf(html, url):
        order.append("trafilatura")
        return {"content": "long enough " * 40, "title": "T", "content_format": "markdown"}

    async def read(html, url):  # pragma: no cover - must not run
        order.append("readability")
        return {}

    monkeypatch.setattr(chain, "_trafilatura", traf)
    monkeypatch.setattr(chain, "_readability", read)
    monkeypatch.setattr(chain, "_newspaper", lambda html, url: None)

    result = asyncio.run(chain.extract_body("<html></html>", "https://example.com/a"))

    assert order == ["trafilatura"]
    assert len(result["content"]) >= 200


def test_extractor_chain_falls_through_and_keeps_longest(monkeypatch) -> None:
    from souwen.providers.runtime_clients.web import _extractor_chain as chain

    def traf(html, url):
        return {"content": "xy", "title": "", "content_format": "text"}

    # _readability 返回可等待对象（run_in_executor future）
    def read(html, url):
        async def _coro():
            return {"content": "mid " * 60, "title": "", "content_format": "markdown"}

        return _coro()

    def news(html, url):
        return None

    monkeypatch.setattr(chain, "_trafilatura", traf)
    monkeypatch.setattr(chain, "_readability", read)
    monkeypatch.setattr(chain, "_newspaper", news)

    result = asyncio.run(chain.extract_body("<html></html>", "https://example.com/a"))

    assert len(result["content"]) >= 200


def test_verification_and_js_shell_detection() -> None:
    from souwen.providers.runtime_clients.web._extractor_chain import looks_like_blocked_content

    assert looks_like_blocked_content("<html><title>Just a moment...</title></html>", "")
    assert looks_like_blocked_content("x" * 30000, "tiny")
    assert not looks_like_blocked_content("<html>ok</html>", "real body " * 50)


def test_content_quality_shared_gate_replaces_63_char_rule() -> None:
    """SPEC 4.3：生产质量门禁统一为 200 字阈值 + 验证页/JS 空壳判定。

    旧规则（≤63 字判 low）在 6 个生产调用点内联；现在它们都走
    content_quality，此测试锁定生产消费语义。
    """

    from souwen.providers.runtime_clients.web._extractor_chain import content_quality

    # 200 字以上：高质量
    assert content_quality("word " * 60) == "high"
    # 63~200 字的正文：低质量（升级候选）——旧规则会误判为 high
    assert content_quality("word " * 20) == "low"
    # 验证页标记：即便拿不到 HTML 也应 low
    assert content_quality("") == "low"
    # 带原始 HTML：JS 空壳（HTML 大、正文短）
    assert content_quality("tiny", html="x" * 30000) == "low"
    # 带原始 HTML：正常短页（HTML 小、正文短）仍 low（升级判定保守）
    assert content_quality("short", html="<html>ok</html>") == "low"


def test_browser_executor_uses_shared_quality_gate() -> None:
    """browser executor 的 quality 字段走共享门禁（63→200 字语义）。"""

    import inspect

    from souwen.server.browser_executor import InProcessBrowserFetchExecutor

    # 不启动浏览器：静态检查 quality 来源是共享门禁
    source = inspect.getsource(InProcessBrowserFetchExecutor)
    assert "content_quality" in source
