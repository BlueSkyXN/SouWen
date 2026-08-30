"""Static Provider v2 declaration for authenticated USPTO ODP Search."""

from souwen.platform.manifest_registry import ProviderManifest


USPTO_ODP_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "uspto_odp",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "uspto_odp-search",
                "capability": "search",
                "export": "UsptoOdpSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "uspto-odp-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["USPTO_API_KEY"]},
        "network": {
            "egress_hosts": ["data.uspto.gov"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["uspto-odp-provider-config-v1"],
        },
    }
)

__all__ = ["USPTO_ODP_PROVIDER_MANIFEST"]
