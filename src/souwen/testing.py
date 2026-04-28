"""Testing helpers for SouWen plugin authors."""

from __future__ import annotations

from typing import Any

from souwen.plugin import Plugin, _coerce_to_plugin
from souwen.registry.adapter import SourceAdapter
from souwen.registry.views import all_adapters, external_plugins


def assert_valid_plugin(plugin_or_entry_point: Any) -> None:
    """Validate that a plugin conforms to the SouWen plugin contract."""
    plugin_name = getattr(plugin_or_entry_point, "name", "contract_test")
    if not isinstance(plugin_name, str) or not plugin_name:
        plugin_name = "contract_test"
    try:
        plugin = _coerce_to_plugin(plugin_or_entry_point, plugin_name=plugin_name)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"Plugin entry point cannot be coerced to Plugin: {exc}") from exc

    assert isinstance(plugin, Plugin), "Plugin entry point did not produce a Plugin instance."

    if plugin.health_check is not None:
        assert callable(plugin.health_check), "Plugin health_check must be callable when defined."
    if plugin.on_startup is not None:
        assert callable(plugin.on_startup), "Plugin on_startup must be callable when defined."
    if plugin.on_shutdown is not None:
        assert callable(plugin.on_shutdown), "Plugin on_shutdown must be callable when defined."

    builtin_names = set(all_adapters()) - set(external_plugins())
    seen_adapter_names: set[str] = set()
    for adapter in plugin.adapters:
        assert isinstance(adapter, SourceAdapter), (
            f"Plugin adapter {adapter!r} must be a SourceAdapter instance."
        )
        assert getattr(adapter, "name", None), "Plugin adapter must define a non-empty name."
        assert getattr(adapter, "domain", None), (
            f"Adapter {adapter.name!r} must define a non-empty domain."
        )
        assert getattr(adapter, "methods", None), (
            f"Adapter {adapter.name!r} must define at least one method."
        )
        assert adapter.name not in seen_adapter_names, (
            f"Adapter name {adapter.name!r} is duplicated within the plugin."
        )
        assert adapter.name not in builtin_names, (
            f"Adapter name {adapter.name!r} conflicts with a built-in source."
        )
        seen_adapter_names.add(adapter.name)
