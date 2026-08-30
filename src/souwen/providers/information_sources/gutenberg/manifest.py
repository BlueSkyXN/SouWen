"""Static Provider v2 manifest for local Project Gutenberg catalog search."""

from souwen.platform.manifest_registry import ProviderManifest

GUTENBERG_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "gutenberg",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "gutenberg-search",
                "capability": "search",
                "export": "GutenbergSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "gutenberg-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {"egress_hosts": [], "proxy_supported": False, "browser_required": False},
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["gutenberg-provider-config-v1"],
        },
    }
)
__all__ = ["GUTENBERG_PROVIDER_MANIFEST"]
