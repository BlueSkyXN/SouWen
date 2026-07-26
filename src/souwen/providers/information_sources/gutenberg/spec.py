"""Reviewed local-store search declaration for Gutenberg."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, LocalStoreDeclaration

GUTENBERG_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="gutenberg",
    adapter_id="gutenberg-search",
    domain="book",
    adapter_reason="local SQLite FTS catalog projection remains in the existing client",
    transport=LocalStoreDeclaration(
        store="local_catalog", protocol="sqlite", operations=("search",)
    ),
    configuration_keys=("enabled",),
)
__all__ = ["GUTENBERG_PROVIDER_SPEC"]
