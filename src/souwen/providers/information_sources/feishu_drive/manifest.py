"""Static Provider v2 manifest for feishu_drive."""

from souwen.platform.manifest_registry import ProviderManifest

FEISHU_DRIVE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "feishu_drive",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "feishu-drive-search",
                "capability": "search",
                "export": "FeishuDriveSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "feishu-drive-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]},
        "network": {
            "egress_hosts": ["open.feishu.cn"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["feishu-drive-provider-config-v1"],
        },
    }
)
