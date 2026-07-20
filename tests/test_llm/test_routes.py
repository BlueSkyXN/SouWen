"""Tests for LLM API route wiring and per-endpoint limiter behavior."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError

from souwen.server.auth import check_search_auth
from souwen.server.routes._common import require_llm_enabled


def _llm_config(*, edition: str = "pro", enabled: bool = True, api_key: str | None = "key"):
    cfg = MagicMock()
    cfg.edition = edition
    cfg.llm.enabled = enabled
    cfg.llm.get_api_key.return_value = api_key
    return cfg


def _route_dependencies(module_name: str, path: str) -> list:
    module = importlib.import_module(module_name)
    route = next(
        route
        for route in module.router.routes
        if isinstance(route, APIRoute) and route.path == path
    )
    return [dependency.dependency for dependency in route.dependencies]


@pytest.mark.parametrize(
    ("module_name", "path", "rate_limit_dependency"),
    [
        (
            "souwen.server.routes.summarize",
            "/summarize",
            "rate_limit_summarize",
        ),
        (
            "souwen.server.routes.fetch_summarize",
            "/fetch/summarize",
            "rate_limit_fetch_summarize",
        ),
    ],
)
def test_llm_routes_check_enabled_before_rate_limit(
    module_name: str,
    path: str,
    rate_limit_dependency: str,
):
    module = importlib.import_module(module_name)
    deps = _route_dependencies(module_name, path)

    assert deps == [
        require_llm_enabled,
        getattr(module, rate_limit_dependency),
        check_search_auth,
    ]


def test_require_llm_enabled_rejects_basic_before_runtime_config(monkeypatch):
    monkeypatch.setattr(
        "souwen.config.get_config",
        lambda: _llm_config(edition="basic", enabled=False, api_key=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_llm_enabled()

    assert exc_info.value.status_code == 403
    assert "LLM requires edition=pro, current edition=basic" in exc_info.value.detail


def test_require_llm_enabled_checks_runtime_config_for_pro(monkeypatch):
    monkeypatch.setattr(
        "souwen.config.get_config",
        lambda: _llm_config(edition="pro", enabled=False, api_key=None),
    )
    with pytest.raises(HTTPException) as disabled_exc:
        require_llm_enabled()
    assert disabled_exc.value.status_code == 503
    assert disabled_exc.value.detail == "LLM feature is not enabled"

    monkeypatch.setattr(
        "souwen.config.get_config",
        lambda: _llm_config(edition="pro", enabled=True, api_key=None),
    )
    with pytest.raises(HTTPException) as missing_key_exc:
        require_llm_enabled()
    assert missing_key_exc.value.status_code == 503
    assert missing_key_exc.value.detail == "LLM service not configured"

    monkeypatch.setattr(
        "souwen.config.get_config",
        lambda: _llm_config(edition="full", enabled=True, api_key="key"),
    )
    require_llm_enabled()


@pytest.mark.parametrize(
    ("module_name", "limiter_attr", "rate_limit_fn", "config_attr"),
    [
        (
            "souwen.server.routes.summarize",
            "_summarize_limiter",
            "rate_limit_summarize",
            "rate_limit_summarize",
        ),
        (
            "souwen.server.routes.fetch_summarize",
            "_fetch_summarize_limiter",
            "rate_limit_fetch_summarize",
            "rate_limit_fetch",
        ),
    ],
)
def test_llm_limiters_refresh_when_config_changes(
    monkeypatch,
    module_name: str,
    limiter_attr: str,
    rate_limit_fn: str,
    config_attr: str,
):
    module = importlib.import_module(module_name)
    cfg = MagicMock()
    cfg.llm = MagicMock()
    setattr(cfg.llm, config_attr, 1)

    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr(module, "get_client_ip", lambda request: "203.0.113.9")
    setattr(module, limiter_attr, None)

    try:
        request = MagicMock()
        getattr(module, rate_limit_fn)(request)
        with pytest.raises(HTTPException) as exc_info:
            getattr(module, rate_limit_fn)(request)
        assert exc_info.value.status_code == 429

        setattr(cfg.llm, config_attr, 2)
        getattr(module, rate_limit_fn)(request)
        assert getattr(module, limiter_attr).max_requests == 2
    finally:
        setattr(module, limiter_attr, None)


async def test_summarize_route_normalizes_sources_for_search_meta(monkeypatch):
    """summarize 请求应先 strip domain/sources，避免成功源被 meta.failed 误报。"""
    from souwen.llm.models import LLMUsage, SummaryResult
    from souwen.models import PaperResult, SearchResponse

    module = importlib.import_module("souwen.server.routes.summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)

    captured: dict = {}

    async def fake_search(query, domain="paper", sources=None, limit=10):
        captured["search"] = {
            "query": query,
            "domain": domain,
            "sources": sources,
            "limit": limit,
        }
        return [
            SearchResponse(
                query=query,
                source="openalex",
                results=[
                    PaperResult(
                        source="openalex",
                        title="Paper",
                        source_url="https://example.com/paper",
                    )
                ],
            )
        ]

    async def fake_summarize(
        query,
        responses,
        mode="brief",
        model=None,
        max_tokens=None,
        temperature=None,
        system_prompt_override=None,
    ):
        captured["summarize"] = {
            "query": query,
            "responses": responses,
            "mode": mode,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system_prompt_override": system_prompt_override,
        }
        return SummaryResult(
            query=query,
            summary="summary",
            mode=mode,
            model="test-model",
            usage=LLMUsage(),
            sources_used=1,
            results_used=1,
        )

    search_mod = importlib.import_module("souwen.search")
    summarize_mod = importlib.import_module("souwen.llm.summarize")
    monkeypatch.setattr(search_mod, "search", fake_search)
    monkeypatch.setattr(summarize_mod, "summarize", fake_summarize)

    body = module.SummarizeRequest(
        query=" agent search ",
        domain=" paper ",
        sources=[" openalex "],
        per_page=3,
    )
    response = await module.api_summarize(body)

    assert captured["search"] == {
        "query": "agent search",
        "domain": "paper",
        "sources": ["openalex"],
        "limit": 3,
    }
    assert response.search_meta.requested == ["openalex"]
    assert response.search_meta.succeeded == ["openalex"]
    assert response.search_meta.failed == []


async def test_summarize_route_redacts_llm_error_detail(monkeypatch):
    """summarize LLM 错误响应不应泄漏 token、Cookie 或 URL query secret。"""
    from souwen.llm.client import LLMError
    from souwen.models import PaperResult, SearchResponse

    module = importlib.import_module("souwen.server.routes.summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)

    async def fake_search(query, domain="paper", sources=None, limit=10):
        return [
            SearchResponse(
                query=query,
                source="openalex",
                results=[
                    PaperResult(
                        source="openalex",
                        title="Paper",
                        source_url="https://example.com/paper",
                    )
                ],
            )
        ]

    secret_error = (
        "provider failed token=llm-secret Cookie: sid=session-secret "
        "callback https://llm.example/cb?apiKey=url-secret&safe=1"
    )

    async def fake_summarize(*args, **kwargs):
        raise LLMError(secret_error)

    search_mod = importlib.import_module("souwen.search")
    summarize_mod = importlib.import_module("souwen.llm.summarize")
    monkeypatch.setattr(search_mod, "search", fake_search)
    monkeypatch.setattr(summarize_mod, "summarize", fake_summarize)

    body = module.SummarizeRequest(query="agent search")
    with pytest.raises(HTTPException) as exc_info:
        await module.api_summarize(body)

    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert "llm-secret" not in detail
    assert "session-secret" not in detail
    assert "url-secret" not in detail
    assert "token:***" in detail
    assert "Cookie:***" in detail
    assert "apiKey=***" in detail
    assert "safe=1" in detail


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "agent", "domain": " "},
        {"query": "   "},
        {"query": "agent", "sources": ["openalex", " "]},
    ],
)
def test_summarize_request_rejects_blank_query_domain_or_source(kwargs):
    """strip 后为空的 query/domain/source 字段应被请求模型拒绝。"""
    module = importlib.import_module("souwen.server.routes.summarize")

    with pytest.raises(ValidationError):
        module.SummarizeRequest(**kwargs)


async def test_fetch_summarize_route_passes_multi_provider_fetch_options(monkeypatch):
    """fetch/summarize 应把 providers + strategy 透传给 LLM fetch-summary 层。"""
    from souwen.llm.models import PageSummaryResult

    module = importlib.import_module("souwen.server.routes.fetch_summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)

    mock_summarize = AsyncMock(
        return_value=PageSummaryResult(
            mode="brief",
            model="test-model",
            total_urls=1,
            total_ok=0,
            total_failed=0,
        )
    )
    monkeypatch.setattr("souwen.llm.fetch_summarize.summarize_pages", mock_summarize)

    body = module.FetchSummarizeRequest(
        urls=["https://example.com"],
        providers=["builtin", "jina_reader"],
        strategy="fanout",
        timeout=12,
    )
    response = await module.api_fetch_summarize(body)

    mock_summarize.assert_awaited_once_with(
        urls=["https://example.com"],
        provider="builtin",
        providers=["builtin", "jina_reader"],
        strategy="fanout",
        timeout=12,
        mode="brief",
        model=None,
        max_tokens=None,
        temperature=None,
        system_prompt_override=None,
    )
    assert response.total_urls == 1


async def test_fetch_summarize_route_normalizes_provider_and_url_whitespace(monkeypatch):
    """fetch/summarize 请求边界应 strip URL/provider 后再校验 provider。"""
    from souwen.llm.models import PageSummaryResult

    module = importlib.import_module("souwen.server.routes.fetch_summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)

    mock_summarize = AsyncMock(
        return_value=PageSummaryResult(
            mode="brief",
            model="test-model",
            total_urls=1,
            total_ok=0,
            total_failed=0,
        )
    )
    monkeypatch.setattr("souwen.llm.fetch_summarize.summarize_pages", mock_summarize)
    monkeypatch.setattr(module, "fetch_providers", lambda: [SimpleNamespace(name="builtin")])

    body = module.FetchSummarizeRequest(
        urls=[" https://example.com "],
        provider=" builtin ",
    )
    await module.api_fetch_summarize(body)

    mock_summarize.assert_awaited_once_with(
        urls=["https://example.com"],
        provider="builtin",
        providers=["builtin"],
        strategy="fallback",
        timeout=30.0,
        mode="brief",
        model=None,
        max_tokens=None,
        temperature=None,
        system_prompt_override=None,
    )


async def test_fetch_summarize_route_normalizes_providers_whitespace(monkeypatch):
    """providers 列表项也应在 registry 校验前归一化。"""
    from souwen.llm.models import PageSummaryResult

    module = importlib.import_module("souwen.server.routes.fetch_summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)

    mock_summarize = AsyncMock(
        return_value=PageSummaryResult(
            mode="brief",
            model="test-model",
            total_urls=1,
            total_ok=0,
            total_failed=0,
        )
    )
    monkeypatch.setattr("souwen.llm.fetch_summarize.summarize_pages", mock_summarize)
    monkeypatch.setattr(
        module,
        "fetch_providers",
        lambda: [SimpleNamespace(name="builtin"), SimpleNamespace(name="jina_reader")],
    )

    body = module.FetchSummarizeRequest(
        urls=["https://example.com"],
        providers=[" builtin ", " jina_reader "],
        strategy="fanout",
    )
    await module.api_fetch_summarize(body)

    mock_summarize.assert_awaited_once_with(
        urls=["https://example.com"],
        provider="builtin",
        providers=["builtin", "jina_reader"],
        strategy="fanout",
        timeout=30.0,
        mode="brief",
        model=None,
        max_tokens=None,
        temperature=None,
        system_prompt_override=None,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"urls": [" "], "provider": "builtin"},
        {"urls": ["https://example.com"], "provider": " "},
        {"urls": ["https://example.com"], "providers": ["builtin", " "]},
    ],
)
def test_fetch_summarize_request_rejects_blank_url_or_provider(kwargs):
    """strip 后为空的 URL/provider 字段应被请求模型拒绝。"""
    module = importlib.import_module("souwen.server.routes.fetch_summarize")

    with pytest.raises(ValidationError):
        module.FetchSummarizeRequest(**kwargs)


async def test_fetch_summarize_route_rejects_invalid_fetch_provider(monkeypatch):
    """fetch/summarize 应和 fetch route 一样用 registry 校验 provider。"""
    module = importlib.import_module("souwen.server.routes.fetch_summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr(module, "fetch_providers", lambda: [SimpleNamespace(name="builtin")])

    mock_summarize = AsyncMock()
    monkeypatch.setattr("souwen.llm.fetch_summarize.summarize_pages", mock_summarize)

    body = module.FetchSummarizeRequest(
        urls=["https://example.com"],
        providers=["builtin", "missing_fetch_provider"],
    )
    with pytest.raises(HTTPException) as exc_info:
        await module.api_fetch_summarize(body)

    assert exc_info.value.status_code == 400
    assert "missing_fetch_provider" in exc_info.value.detail
    mock_summarize.assert_not_awaited()


async def test_fetch_summarize_route_redacts_llm_error_detail(monkeypatch):
    """fetch/summarize LLM 错误响应不应泄漏 token、Cookie 或 URL query secret。"""
    from souwen.llm.client import LLMError

    module = importlib.import_module("souwen.server.routes.fetch_summarize")
    cfg = MagicMock()
    cfg.llm.default_mode = "brief"
    cfg.llm.system_prompt = None
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr(module, "fetch_providers", lambda: [SimpleNamespace(name="builtin")])

    secret_error = (
        "provider failed token=llm-secret Cookie: sid=session-secret "
        "callback https://llm.example/cb?apiKey=url-secret&safe=1"
    )

    async def fake_summarize_pages(*args, **kwargs):
        raise LLMError(secret_error)

    monkeypatch.setattr("souwen.llm.fetch_summarize.summarize_pages", fake_summarize_pages)

    body = module.FetchSummarizeRequest(urls=["https://example.com"], provider="builtin")
    with pytest.raises(HTTPException) as exc_info:
        await module.api_fetch_summarize(body)

    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert "llm-secret" not in detail
    assert "session-secret" not in detail
    assert "url-secret" not in detail
    assert "token:***" in detail
    assert "Cookie:***" in detail
    assert "apiKey=***" in detail
    assert "safe=1" in detail
