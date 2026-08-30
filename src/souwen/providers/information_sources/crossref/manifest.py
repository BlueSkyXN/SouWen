"""Static Provider v2 manifest for Crossref."""

from souwen.platform.manifest_registry import ProviderManifest

CROSSREF_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "crossref",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "crossref-search",
                "capability": "search",
                "export": "CrossrefSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "crossref-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.crossref.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["crossref-provider-config-v1"],
        },
    }
)
