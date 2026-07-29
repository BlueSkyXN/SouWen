from souwen.platform.manifest_registry import ProviderManifest

WAYBACK_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "wayback",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "wayback-fetch",
                "capability": "fetch",
                "export": "WaybackFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "wayback-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["archive.org", "web.archive.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["wayback-provider-config-v1"],
        },
    }
)
