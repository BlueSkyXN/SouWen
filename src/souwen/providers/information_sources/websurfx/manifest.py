from souwen.platform.manifest_registry import ProviderManifest

WEBSURFX_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "websurfx",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "websurfx-search",
                "capability": "search",
                "export": "WebsurfxSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "websurfx-self-hosted-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "base_url"],
        },
        "secrets": {"references": [], "optional_references": []},
        "network": {
            "egress_hosts": [],
            "target_egress": "configured_self_hosted_endpoint",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["websurfx-self-hosted-provider-config-v1"],
        },
    }
)
