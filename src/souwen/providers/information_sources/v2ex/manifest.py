from souwen.platform.manifest_registry import ProviderManifest

V2EX_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "v2ex",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "v2ex-search",
                "capability": "search",
                "export": "V2EXSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "v2ex-provider-config-v1",
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
            "config_schema_versions": ["v2ex-provider-config-v1"],
        },
    }
)
__all__ = ["V2EX_PROVIDER_MANIFEST"]
