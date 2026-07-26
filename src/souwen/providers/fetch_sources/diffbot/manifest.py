"""Static Provider v2 declaration for Diffbot Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

DIFFBOT_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "diffbot",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "diffbot-fetch",
                "capability": "fetch",
                "export": "DiffbotFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "diffbot-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["DIFFBOT_API_TOKEN"]},
        "network": {
            "egress_hosts": ["api.diffbot.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["diffbot-provider-config-v1"],
        },
    }
)

__all__ = ["DIFFBOT_PROVIDER_MANIFEST"]
