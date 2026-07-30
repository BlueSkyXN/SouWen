"""Static Provider v2 declaration for Apify Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

APIFY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "apify",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "apify-fetch",
                "capability": "fetch",
                "export": "ApifyFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "apify-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["APIFY_API_TOKEN"]},
        "network": {
            "egress_hosts": ["api.apify.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["apify-provider-config-v1"],
        },
    }
)

__all__ = ["APIFY_PROVIDER_MANIFEST"]
