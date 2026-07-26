"""Static Provider v2 manifest for linkup."""

from souwen.platform.manifest_registry import ProviderManifest

LINKUP_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "linkup",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "linkup-search",
                "capability": "search",
                "export": "LinkupSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "linkup-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["LINKUP_API_KEY"]},
        "network": {
            "egress_hosts": ["api.linkup.so"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["linkup-provider-config-v1"],
        },
    }
)
