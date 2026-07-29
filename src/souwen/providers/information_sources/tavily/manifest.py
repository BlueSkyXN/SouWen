"""Static Provider v2 manifest for tavily."""

from souwen.platform.manifest_registry import ProviderManifest

TAVILY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "tavily",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "tavily-search",
                "capability": "search",
                "export": "TavilySearchProvider",
                "availability": "configured",
            },
            {
                "id": "tavily-fetch",
                "capability": "fetch",
                "export": "TavilyFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "tavily-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["TAVILY_API_KEY"]},
        "network": {
            "egress_hosts": ["api.tavily.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["tavily-provider-config-v1"],
        },
    }
)
