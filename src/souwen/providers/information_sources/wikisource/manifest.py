"""Static Provider v2 manifest for bounded anonymous Wikisource search."""

from souwen.platform.manifest_registry import ProviderManifest

WIKISOURCE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "wikisource",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "wikisource-search",
                "capability": "search",
                "export": "WikisourceSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "wikisource-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["zh.wikisource.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["wikisource-provider-config-v1"],
        },
    }
)
__all__ = ["WIKISOURCE_PROVIDER_MANIFEST"]
