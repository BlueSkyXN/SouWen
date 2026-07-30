"""Static Provider v2 manifest for serper."""

from souwen.platform.manifest_registry import ProviderManifest

SERPER_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "serper",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "serper-search",
                "capability": "search",
                "export": "SerperSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "serper-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["SERPER_API_KEY"]},
        "network": {
            "egress_hosts": ["google.serper.dev"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["serper-provider-config-v1"],
        },
    }
)
