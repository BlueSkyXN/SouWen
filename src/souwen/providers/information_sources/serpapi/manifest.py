"""Static Provider v2 manifest for serpapi."""

from souwen.platform.manifest_registry import ProviderManifest

SERPAPI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "serpapi",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "serpapi-search",
                "capability": "search",
                "export": "SerpApiSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "serpapi-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SERPAPI_API_KEY"]},
        "network": {
            "egress_hosts": ["serpapi.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["serpapi-provider-config-v1"],
        },
    }
)
