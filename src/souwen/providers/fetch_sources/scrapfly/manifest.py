"""Static Provider v2 declaration for Scrapfly Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

SCRAPFLY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "scrapfly",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "scrapfly-fetch",
                "capability": "fetch",
                "export": "ScrapflyFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "scrapfly-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SCRAPFLY_API_KEY"]},
        "network": {
            "egress_hosts": ["api.scrapfly.io"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["scrapfly-provider-config-v1"],
        },
    }
)

__all__ = ["SCRAPFLY_PROVIDER_MANIFEST"]
