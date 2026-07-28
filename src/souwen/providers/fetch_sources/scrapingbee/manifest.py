"""Static Provider v2 declaration for ScrapingBee Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

SCRAPINGBEE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "scrapingbee",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "scrapingbee-fetch",
                "capability": "fetch",
                "export": "ScrapingBeeFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "scrapingbee-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SCRAPINGBEE_API_KEY"]},
        "network": {
            "egress_hosts": ["app.scrapingbee.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["scrapingbee-provider-config-v1"],
        },
    }
)

__all__ = ["SCRAPINGBEE_PROVIDER_MANIFEST"]
