from souwen.platform.manifest_registry import ProviderManifest

JUEJIN_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "juejin",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "juejin-search",
                "capability": "search",
                "export": "JuejinSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "juejin-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.juejin.cn"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["juejin-provider-config-v1"],
        },
    }
)
__all__ = ["JUEJIN_PROVIDER_MANIFEST"]
