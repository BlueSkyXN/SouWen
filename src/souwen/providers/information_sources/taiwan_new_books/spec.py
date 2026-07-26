"""Reviewed local-store search declaration for Taiwan new-books."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, LocalStoreDeclaration

TAIWAN_NEW_BOOKS_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="taiwan_new_books",
    adapter_id="taiwan_new_books-search",
    domain="book",
    adapter_reason="local SQLite ISBN catalog projection remains in the existing client",
    transport=LocalStoreDeclaration(
        store="local_catalog", protocol="sqlite", operations=("search",)
    ),
    configuration_keys=("enabled",),
)
__all__ = ["TAIWAN_NEW_BOOKS_PROVIDER_SPEC"]
