"""Reviewed local-store search declaration for Gutenberg."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LocalStoreDeclaration

GUTENBERG_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="gutenberg",
    adapter_id="gutenberg-search",
    domain="book",
    bridge_reason="local SQLite FTS catalog projection remains in the legacy client",
    transport=LocalStoreDeclaration(
        store="local_catalog", protocol="sqlite", operations=("search",)
    ),
    configuration_keys=("enabled",),
)
__all__ = ["GUTENBERG_PROVIDER_SPEC"]
