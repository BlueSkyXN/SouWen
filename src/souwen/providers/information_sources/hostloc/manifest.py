from souwen.platform.manifest_registry import ProviderManifest

HOSTLOC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "hostloc",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "hostloc-search",
                "capability": "search",
                "export": "HostLocSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "hostloc-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["html.duckduckgo.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["hostloc-provider-config-v1"],
        },
    }
)
__all__ = ["HOSTLOC_PROVIDER_MANIFEST"]
