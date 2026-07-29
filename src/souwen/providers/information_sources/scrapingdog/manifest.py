"""Static Provider v2 manifest for scrapingdog."""

from souwen.platform.manifest_registry import ProviderManifest

SCRAPINGDOG_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "scrapingdog",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "scrapingdog-search",
                "capability": "search",
                "export": "ScrapingDogSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "scrapingdog-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SCRAPINGDOG_API_KEY"]},
        "network": {
            "egress_hosts": ["api.scrapingdog.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["scrapingdog-provider-config-v1"],
        },
    }
)
