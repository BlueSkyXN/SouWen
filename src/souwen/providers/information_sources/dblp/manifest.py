"""Static Provider v2 manifest for DBLP."""

from souwen.platform.manifest_registry import ProviderManifest

DBLP_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "dblp",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "dblp-search",
                "capability": "search",
                "export": "DblpSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "dblp-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["dblp.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["dblp-provider-config-v1"],
        },
    }
)
