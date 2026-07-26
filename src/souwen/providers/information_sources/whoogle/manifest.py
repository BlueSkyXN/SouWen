from souwen.platform.manifest_registry import ProviderManifest

WHOOGLE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "whoogle",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "whoogle-search",
                "capability": "search",
                "export": "WhoogleSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "whoogle-self-hosted-provider-config-v1",
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
            "config_schema_versions": ["whoogle-self-hosted-provider-config-v1"],
        },
    }
)
