"""Static Provider v2 manifest for exa."""

from souwen.platform.manifest_registry import ProviderManifest

EXA_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "exa",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "exa-search",
                "capability": "search",
                "export": "ExaSearchProvider",
                "availability": "configured",
            },
            {
                "id": "exa-fetch",
                "capability": "fetch",
                "export": "ExaFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "exa-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["EXA_API_KEY"]},
        "network": {
            "egress_hosts": ["api.exa.ai"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["exa-provider-config-v1"],
        },
    }
)
