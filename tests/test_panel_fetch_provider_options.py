"""Panel Fetch must use the generated target SDK without a local provider catalog."""

from __future__ import annotations

from pathlib import Path


def test_panel_fetch_uses_generated_sdk_without_legacy_provider_options() -> None:
    """Fetch delegates provider selection to the target API instead of duplicating registry data."""
    legacy_hook = Path("panel/src/core/hooks/useFetchPage.ts")
    app_path = Path("panel/src/CalmPrecisionApp.tsx")
    app = app_path.read_text(encoding="utf-8")
    fetch_page = app.split("function FetchPage()", maxsplit=1)[1].split(
        "function ProvidersPage()", maxsplit=1
    )[0]

    assert not legacy_hook.exists()
    assert "client.fetch(" in fetch_page
    assert "DEFAULT_FETCH_PROVIDER_OPTIONS" not in app
    assert "fetch_providers" not in app
