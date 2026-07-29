"""Static Provider v2 manifest for wikipedia."""

from souwen.platform.manifest_registry import ProviderManifest

WIKIPEDIA_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "wikipedia",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "wikipedia-search",
                "capability": "search",
                "export": "WikipediaSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "wikipedia-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["zh.wikipedia.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["wikipedia-provider-config-v1"],
        },
    }
)
