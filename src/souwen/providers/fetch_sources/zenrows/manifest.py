"""Static Provider v2 declaration for ZenRows Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

ZENROWS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "zenrows",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "zenrows-fetch",
                "capability": "fetch",
                "export": "ZenRowsFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "zenrows-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["ZENROWS_API_KEY"]},
        "network": {
            "egress_hosts": ["api.zenrows.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["zenrows-provider-config-v1"],
        },
    }
)

__all__ = ["ZENROWS_PROVIDER_MANIFEST"]
