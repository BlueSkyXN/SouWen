"""Static Provider v2 declaration for ScraperAPI Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

SCRAPERAPI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "scraperapi",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "scraperapi-fetch",
                "capability": "fetch",
                "export": "ScraperAPIFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "scraperapi-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SCRAPERAPI_API_KEY"]},
        "network": {
            "egress_hosts": ["api.scraperapi.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["scraperapi-provider-config-v1"],
        },
    }
)

__all__ = ["SCRAPERAPI_PROVIDER_MANIFEST"]
