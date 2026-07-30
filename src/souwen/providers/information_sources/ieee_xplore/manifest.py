"""Static Provider v2 manifest for IEEE Xplore."""

from souwen.platform.manifest_registry import ProviderManifest

IEEE_XPLORE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "ieee_xplore",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "ieee-xplore-search",
                "capability": "search",
                "export": "IeeeXploreSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "ieee-xplore-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["IEEE_API_KEY"]},
        "network": {
            "egress_hosts": ["ieeexploreapi.ieee.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["ieee-xplore-provider-config-v1"],
        },
    }
)
