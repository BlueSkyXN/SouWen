"""Panel fetch provider fallback should stay aligned with the registry."""

from __future__ import annotations

import re
from pathlib import Path

from souwen.registry import external_plugins, fetch_providers


def test_panel_fetch_provider_fallback_matches_builtin_registry() -> None:
    """The offline panel fallback must include every built-in fetch provider."""
    hook_path = Path("panel/src/core/hooks/useFetchPage.ts")
    text = hook_path.read_text(encoding="utf-8")
    match = re.search(
        r"DEFAULT_FETCH_PROVIDER_OPTIONS: FetchProviderOption\[\] = \[(.*?)\]\n\nexport const MAX_URLS",
        text,
        re.DOTALL,
    )
    assert match is not None

    panel_names = re.findall(r"value: '([^']+)'", match.group(1))
    registry_names = [
        adapter.name for adapter in fetch_providers() if adapter.name not in external_plugins()
    ]

    assert panel_names[0] == "builtin"
    assert set(panel_names) == set(registry_names)
