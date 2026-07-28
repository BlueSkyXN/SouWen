"""Static Provider v2 declaration for authenticated PQAI Search."""

from souwen.platform.manifest_registry import ProviderManifest


PQAI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "pqai",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "pqai-search",
                "capability": "search",
                "export": "PqaiSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "pqai-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["PQAI_API_TOKEN"]},
        "network": {
            "egress_hosts": ["api.projectpq.ai"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["pqai-provider-config-v1"],
        },
    }
)

__all__ = ["PQAI_PROVIDER_MANIFEST"]
