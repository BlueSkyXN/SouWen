"""Static Provider v2 manifest for zhipuai."""

from souwen.platform.manifest_registry import ProviderManifest

ZHIPUAI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "zhipuai",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "zhipuai-search",
                "capability": "search",
                "export": "ZhipuAISearchSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "zhipuai-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["ZHIPUAI_API_KEY"]},
        "network": {
            "egress_hosts": ["open.bigmodel.cn"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["zhipuai-provider-config-v1"],
        },
    }
)
