"""Static Provider v2 manifest for CORE."""

from souwen.platform.manifest_registry import ProviderManifest

CORE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "core",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "core-search",
                "capability": "search",
                "export": "CoreSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "core-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["CORE_API_KEY"]},
        "network": {
            "egress_hosts": ["api.core.ac.uk"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["core-provider-config-v1"],
        },
    }
)
