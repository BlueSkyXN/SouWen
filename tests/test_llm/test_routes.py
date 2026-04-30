"""Tests for LLM API route wiring and per-endpoint limiter behavior."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException
from fastapi.routing import APIRoute

from souwen.server.auth import check_search_auth
from souwen.server.routes._common import require_llm_enabled


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
