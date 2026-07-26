"""Static Provider v2 manifest for anonymous Open Library search."""

from souwen.platform.manifest_registry import ProviderManifest

OPEN_LIBRARY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "open_library",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "open_library-search",
                "capability": "search",
                "export": "OpenLibrarySearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "open-library-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["openlibrary.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["open-library-provider-config-v1"],
        },
    }
)
__all__ = ["OPEN_LIBRARY_PROVIDER_MANIFEST"]
