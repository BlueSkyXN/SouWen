"""Static Provider v2 manifest for HAL."""

from souwen.platform.manifest_registry import ProviderManifest

HAL_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "hal",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "hal-search",
                "capability": "search",
                "export": "HalSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "hal-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.archives-ouvertes.fr"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["hal-provider-config-v1"],
        },
    }
)
