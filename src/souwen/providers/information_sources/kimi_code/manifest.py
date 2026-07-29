"""Static Provider v2 manifest for kimi_code."""

from souwen.platform.manifest_registry import ProviderManifest

KIMI_CODE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "kimi_code",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search", "fetch"],
        "adapters": [
            {
                "id": "kimi_code-search",
                "capability": "search",
                "export": "KimiCodeSearchProvider",
                "availability": "configured",
            },
            {
                "id": "kimi_code-fetch",
                "capability": "fetch",
                "export": "KimiCodeFetchProvider",
                "availability": "configured",
            },
        ],
        "configuration": {
            "schema_reference": "kimi-code-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["KIMI_CODE_API_KEY"]},
        "network": {
            "egress_hosts": ["api.kimi.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["kimi-code-provider-config-v1"],
        },
    }
)
