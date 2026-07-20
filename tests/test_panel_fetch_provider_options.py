"""Panel fetch provider display definitions should stay aligned with the registry."""

from __future__ import annotations

import re
from pathlib import Path

from souwen.registry import external_plugins, fetch_providers


def test_panel_fetch_provider_definitions_match_builtin_registry() -> None:
    """Static labels/order cover built-ins without becoming an executable fallback."""
    hook_path = Path("panel/src/core/hooks/useFetchPage.ts")
    text = hook_path.read_text(encoding="utf-8")
    match = re.search(
        r"DEFAULT_FETCH_PROVIDER_OPTIONS: FetchProviderDefinition\[\] = "
        r"\[(.*?)\]\n\nexport const MAX_URLS",
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
    assert "useState<FetchProviderOption[]>([])" in text
    assert "setProviderOptions(DEFAULT_FETCH_PROVIDER_OPTIONS)" not in text
