"""Static Provider v2 declaration for anonymous PMC Search."""

from souwen.platform.manifest_registry import ProviderManifest


PMC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "pmc",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "pmc-search",
                "capability": "search",
                "export": "PmcSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "pmc-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["PUBMED_API_KEY"]},
        "network": {
            "egress_hosts": ["eutils.ncbi.nlm.nih.gov"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["pmc-provider-config-v1"],
        },
    }
)

__all__ = ["PMC_PROVIDER_MANIFEST"]
