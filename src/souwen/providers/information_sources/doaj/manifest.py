"""Static Provider v2 manifest for DOAJ."""

from souwen.platform.manifest_registry import ProviderManifest

DOAJ_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "doaj",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "doaj-search",
                "capability": "search",
                "export": "DoajSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "doaj-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["DOAJ_API_KEY"]},
        "network": {
            "egress_hosts": ["doaj.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["doaj-provider-config-v1"],
        },
    }
)
