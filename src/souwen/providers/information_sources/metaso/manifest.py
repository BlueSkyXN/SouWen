"""Static Provider v2 manifest for metaso."""

from souwen.platform.manifest_registry import ProviderManifest

METASO_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "metaso",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "metaso-search",
                "capability": "search",
                "export": "MetasoSearchProvider",
                "availability": "configured",
            },
            {
                "id": "metaso-fetch",
                "capability": "fetch",
                "export": "MetasoFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "metaso-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["METASO_API_KEY"]},
        "network": {
            "egress_hosts": ["metaso.cn"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["metaso-provider-config-v1"],
        },
    }
)
