"""Regression checks for the retired MCP product surface."""

from __future__ import annotations

import importlib.util


def test_mcp_modules_are_not_importable() -> None:
    for module_name in (
        "souwen.integrations.mcp",
        "souwen.integrations.mcp_server",
        "souwen.web.mcp_client",
        "souwen.web.mcp_fetch",
        "souwen.cli.mcp",
    ):
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None


def test_mcp_is_not_a_registered_fetch_provider() -> None:
    from souwen.registry import get
    from souwen.registry.views import fetch_providers

    assert get("mcp") is None
    assert "mcp" not in {adapter.name for adapter in fetch_providers()}


def test_mcp_routes_are_not_mounted() -> None:
    from souwen.server.app import app

    paths = {route.path for route in app.router.routes if hasattr(route, "path")}
    assert "/mcp" not in paths
    assert "/mcp/sse" not in paths
