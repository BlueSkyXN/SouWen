"""Public API documentation stays aligned with the target contract."""

from pathlib import Path


def test_api_reference_mentions_every_target_operation() -> None:
    text = Path("docs/api-reference.md").read_text(encoding="utf-8")
    for path in (
        "/api/v1/search",
        "/api/v1/llm-search",
        "/api/v1/fetch",
        "/api/v1/providers",
        "/health",
        "/healthz",
        "/readiness",
        "/readyz",
    ):
        assert f"`{path}`" in text


def test_api_reference_does_not_document_retired_routes() -> None:
    text = Path("docs/api-reference.md").read_text(encoding="utf-8")
    for path in (
        "/api/v1/sources",
        "/api/v1/search/paper",
        "/api/v1/citations/count",
        "/api/v1/admin/warp",
        "/api/v1/admin/sources/config",
    ):
        assert f"`{path}`" not in text
