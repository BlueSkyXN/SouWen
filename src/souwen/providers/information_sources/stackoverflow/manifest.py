"""Static Provider v2 manifest for stackoverflow."""

from souwen.platform.manifest_registry import ProviderManifest

STACKOVERFLOW_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "stackoverflow",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "stackoverflow-search",
                "capability": "search",
                "export": "StackOverflowSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "stackoverflow-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["STACKOVERFLOW_API_KEY"]},
        "network": {
            "egress_hosts": ["api.stackexchange.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["stackoverflow-provider-config-v1"],
        },
    }
)
