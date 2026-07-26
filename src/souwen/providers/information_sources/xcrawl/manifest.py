"""Static Provider v2 manifest for xcrawl."""

from souwen.platform.manifest_registry import ProviderManifest

XCRAWL_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "xcrawl",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "xcrawl-search",
                "capability": "search",
                "export": "XCrawlSearchProvider",
                "availability": "configured",
            },
            {
                "id": "xcrawl-fetch",
                "capability": "fetch",
                "export": "XCrawlFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "xcrawl-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["XCRAWL_API_KEY"]},
        "network": {
            "egress_hosts": ["api.xcrawl.dev"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["xcrawl-provider-config-v1"],
        },
    }
)
