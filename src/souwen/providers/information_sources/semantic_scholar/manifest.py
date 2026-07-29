"""Static Provider v2 manifest for Semantic Scholar."""

from souwen.platform.manifest_registry import ProviderManifest

SEMANTIC_SCHOLAR_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "semantic_scholar",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "semantic-scholar-search",
                "capability": "search",
                "export": "SemanticScholarSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "semantic-scholar-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["SEMANTIC_SCHOLAR_API_KEY"]},
        "network": {
            "egress_hosts": ["api.semanticscholar.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["semantic-scholar-provider-config-v1"],
        },
    }
)
