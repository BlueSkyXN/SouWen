"""Static Provider v2 manifest for linuxdo."""

from souwen.platform.manifest_registry import ProviderManifest

LINUXDO_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "linuxdo",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "linuxdo-search",
                "capability": "search",
                "export": "LinuxDoSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "linuxdo-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["linux.do"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["linuxdo-provider-config-v1"],
        },
    }
)
