"""Static Provider v2 manifest for Zotero."""

from souwen.platform.manifest_registry import ProviderManifest

ZOTERO_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "zotero",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "zotero-search",
                "capability": "search",
                "export": "ZoteroSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "zotero-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "library_id", "library_type"],
        },
        "secrets": {"references": ["ZOTERO_API_KEY"]},
        "network": {
            "egress_hosts": ["api.zotero.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["zotero-provider-config-v1"],
        },
    }
)
