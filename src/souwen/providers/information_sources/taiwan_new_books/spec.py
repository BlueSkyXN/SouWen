"""Reviewed local-store search declaration for Taiwan new-books."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LocalStoreDeclaration

TAIWAN_NEW_BOOKS_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="taiwan_new_books",
    adapter_id="taiwan_new_books-search",
    domain="book",
    bridge_reason="local SQLite ISBN catalog projection remains in the legacy client",
    transport=LocalStoreDeclaration(
        store="local_catalog", protocol="sqlite", operations=("search",)
    ),
    configuration_keys=("enabled",),
)
__all__ = ["TAIWAN_NEW_BOOKS_PROVIDER_SPEC"]
