"""Static Provider v2 manifest for facebook."""

from souwen.platform.manifest_registry import ProviderManifest

FACEBOOK_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "facebook",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "facebook-search",
                "capability": "search",
                "export": "FacebookSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "facebook-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"]},
        "network": {
            "egress_hosts": ["graph.facebook.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["facebook-provider-config-v1"],
        },
    }
)
