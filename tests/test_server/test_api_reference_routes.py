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
        {
            route.path
            for route in app.routes
            if route.path in {"/health", "/readiness"} or route.path.startswith("/api/v1")
        }
    )

    missing = [path for path in route_paths if path not in docs]
    assert missing == []
