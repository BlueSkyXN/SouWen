"""Static Provider v2 manifest for local Taiwan new-books catalog search."""

from souwen.platform.manifest_registry import ProviderManifest

TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "taiwan_new_books",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "taiwan_new_books-search",
                "capability": "search",
                "export": "TaiwanNewBooksSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "taiwan-new-books-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {"egress_hosts": [], "proxy_supported": False, "browser_required": False},
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["taiwan-new-books-provider-config-v1"],
        },
    }
)
__all__ = ["TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST"]
