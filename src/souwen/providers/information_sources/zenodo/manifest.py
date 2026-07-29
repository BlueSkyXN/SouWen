"""Static Provider v2 manifest for Zenodo."""

from souwen.platform.manifest_registry import ProviderManifest

ZENODO_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "zenodo",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "zenodo-search",
                "capability": "search",
                "export": "ZenodoSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "zenodo-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["ZENODO_ACCESS_TOKEN"]},
        "network": {
            "egress_hosts": ["zenodo.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["zenodo-provider-config-v1"],
        },
    }
)
