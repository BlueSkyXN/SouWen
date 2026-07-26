"""Static Provider v2 manifest for aliyun_iqs."""

from souwen.platform.manifest_registry import ProviderManifest

ALIYUN_IQS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "aliyun_iqs",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "aliyun-iqs-search",
                "capability": "search",
                "export": "AliyunIQSSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "aliyun-iqs-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["ALIYUN_IQS_API_KEY"]},
        "network": {
            "egress_hosts": ["cloud-iqs.aliyuncs.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["aliyun-iqs-provider-config-v1"],
        },
    }
)
