"""Static Provider v2 manifest for twitter."""

from souwen.platform.manifest_registry import ProviderManifest

TWITTER_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "twitter",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "twitter-search",
                "capability": "search",
                "export": "TwitterSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "twitter-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["TWITTER_BEARER_TOKEN"]},
        "network": {
            "egress_hosts": ["api.twitter.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["twitter-provider-config-v1"],
        },
    }
)
