"""Static Provider v2 manifest for firecrawl."""

from souwen.platform.manifest_registry import ProviderManifest

FIRECRAWL_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "firecrawl",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "firecrawl-search",
                "capability": "search",
                "export": "FirecrawlSearchProvider",
                "availability": "configured",
            },
            {
                "id": "firecrawl-fetch",
                "capability": "fetch",
                "export": "FirecrawlFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "firecrawl-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["FIRECRAWL_API_KEY"]},
        "network": {
            "egress_hosts": ["api.firecrawl.dev"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["firecrawl-provider-config-v1"],
        },
    }
)
