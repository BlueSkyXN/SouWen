"""Static Provider v2 manifest for Europe PMC."""

from souwen.platform.manifest_registry import ProviderManifest

EUROPEPMC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "europepmc",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "europepmc-search",
                "capability": "search",
                "export": "EuropePmcSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "europepmc-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["www.ebi.ac.uk"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["europepmc-provider-config-v1"],
        },
    }
)
