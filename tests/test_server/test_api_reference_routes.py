"""API reference route coverage tests."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="server extras not installed")


def test_api_reference_mentions_all_public_routes() -> None:
    """Every public/server API route should be discoverable in docs/api-reference.md."""
    from souwen.server.app import app

    docs = Path("docs/api-reference.md").read_text(encoding="utf-8")
    route_paths = sorted(
        path
        for path in app.openapi()["paths"]
        if path in {"/health", "/readiness"} or path.startswith("/api/v1")
    )

    missing = [path for path in route_paths if path not in docs]
    assert missing == []


def test_api_reference_fetch_provider_lists_match_registry() -> None:
    """Hand-written fetch provider lists should stay aligned with the registry."""
    from souwen.registry import external_plugins, fetch_providers

    docs = Path("docs/api-reference.md").read_text(encoding="utf-8")
    provider_names = {
        adapter.name for adapter in fetch_providers() if adapter.name not in external_plugins()
    }
    provider_lines = [
        line
        for line in docs.splitlines()
        if "builtin" in line and "deepwiki" in line and ("提供者:" in line or "可选：" in line)
    ]

    assert len(provider_lines) >= 3
    for line in provider_lines:
        missing = [name for name in sorted(provider_names) if name not in line]
        assert missing == []
    assert f"支持 {len(provider_names)} 个提供者" in docs


def test_api_reference_fetch_result_fields_match_model() -> None:
    """FetchResult docs should list every public model field."""
    from souwen.models import FetchResult

    docs = Path("docs/api-reference.md").read_text(encoding="utf-8")
    section = docs.split("### FetchResult", 1)[1].split("### FetchResponse", 1)[0]

    missing = [name for name in FetchResult.model_fields if name not in section]
    assert missing == []


def test_api_reference_fetch_response_fields_match_model() -> None:
    """FetchResponse docs should list every public model field."""
    from souwen.models import FetchResponse

    docs = Path("docs/api-reference.md").read_text(encoding="utf-8")
    section = docs.split("### FetchResponse", 1)[1].split("### SearchResponse", 1)[0]

    missing = [name for name in FetchResponse.model_fields if name not in section]
    assert missing == []


def test_api_reference_fetch_summarize_request_fields_match_model() -> None:
    """Fetch+summarize request docs should list every public request field."""
    from souwen.server.routes.fetch_summarize import FetchSummarizeRequest

    docs = Path("docs/api-reference.md").read_text(encoding="utf-8")
    section = docs.split("#### `POST /api/v1/fetch/summarize`", 1)[1].split(
        "## MCP 工具",
        1,
    )[0]

    missing = [name for name in FetchSummarizeRequest.model_fields if name not in section]
    assert missing == []
