from __future__ import annotations

import importlib

import anyio
import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException
from fastapi.routing import APIRoute

from souwen.feature_matrix import SURFACE_ROUTE_MIN_EDITIONS, route_min_edition
from souwen.server.app import app
from souwen.server.routes._common import require_llm_enabled


def _module_route_paths_with_dependency(module_name: str, dependency) -> set[str]:
    module = importlib.import_module(module_name)
    paths: set[str] = set()
    for route in module.router.routes:
        if not isinstance(route, APIRoute):
            continue
        dependencies = [item.dependency for item in route.dependencies]
        if dependency in dependencies:
            paths.add(f"/api/v1{route.path}")
    return paths


def test_declared_surface_routes_exist_in_fastapi_app() -> None:
    """Route declarations in feature_matrix should point at real app routes."""

    app_routes = set(app.openapi()["paths"])

    assert set(SURFACE_ROUTE_MIN_EDITIONS) <= app_routes
    assert route_min_edition("/api/v1/summarize") == "pro"
    assert route_min_edition("/api/v1/fetch/summarize") == "pro"
    assert route_min_edition("/api/v1/whoami") is None


def test_llm_gated_routes_are_declared_as_pro_surface_routes() -> None:
    """Routes using require_llm_enabled should be represented in feature_matrix."""

    llm_route_paths = set()
    for module_name in (
        "souwen.server.routes.summarize",
        "souwen.server.routes.fetch_summarize",
    ):
        llm_route_paths.update(
            _module_route_paths_with_dependency(module_name, require_llm_enabled)
        )

    assert llm_route_paths == {
        path for path, min_edition in SURFACE_ROUTE_MIN_EDITIONS.items() if min_edition == "pro"
    }


def test_fetch_summarize_maps_edition_denied_provider_to_403(monkeypatch) -> None:
    """Fetch+summarize should match /fetch provider edition behavior."""

    from souwen.config import get_config
    from souwen.server.routes import fetch_summarize as route_module

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    get_config.cache_clear()
    body = route_module.FetchSummarizeRequest(
        urls=["https://example.com"],
        providers=["jina_reader"],
    )

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(route_module.api_fetch_summarize, body)

    assert exc_info.value.status_code == 403
    assert "fetch provider 'jina_reader' requires edition=pro" in exc_info.value.detail
