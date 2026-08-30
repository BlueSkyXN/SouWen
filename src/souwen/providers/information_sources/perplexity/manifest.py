"""Static Provider v2 manifest for perplexity."""

from souwen.platform.manifest_registry import ProviderManifest

PERPLEXITY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "perplexity",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "perplexity-search",
                "capability": "search",
                "export": "PerplexitySearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "perplexity-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["PERPLEXITY_API_KEY"]},
        "network": {
            "egress_hosts": ["api.perplexity.ai"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["perplexity-provider-config-v1"],
        },
    }
)
