"""Static Provider v2 manifest for keenable."""

from souwen.platform.manifest_registry import ProviderManifest

KEENABLE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "keenable",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "keenable-search",
                "capability": "search",
                "export": "KeenableSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "keenable-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["KEENABLE_API_KEY"]},
        "network": {
            "egress_hosts": ["api.keenable.ai"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["keenable-provider-config-v1"],
        },
    }
)
