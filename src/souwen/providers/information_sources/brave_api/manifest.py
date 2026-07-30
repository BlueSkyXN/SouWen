"""Static Provider v2 manifest for brave_api."""

from souwen.platform.manifest_registry import ProviderManifest

BRAVE_API_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "brave_api",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "brave-api-search",
                "capability": "search",
                "export": "BraveApiSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "brave-api-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["BRAVE_API_KEY"]},
        "network": {
            "egress_hosts": ["api.search.brave.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["brave-api-provider-config-v1"],
        },
    }
)
