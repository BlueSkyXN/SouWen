"""Static Provider v2 declaration for DeepWiki Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

DEEPWIKI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "deepwiki",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "deepwiki-fetch",
                "capability": "fetch",
                "export": "DeepWikiFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "deepwiki-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["JINA_API_KEY"]},
        "network": {
            "egress_hosts": ["deepwiki.com", "r.jina.ai"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["deepwiki-provider-config-v1"],
        },
    }
)

__all__ = ["DEEPWIKI_PROVIDER_MANIFEST"]
