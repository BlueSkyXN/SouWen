"""Static Provider v2 manifest for anonymous Figshare article search."""

from souwen.platform.manifest_registry import ProviderManifest


FIGSHARE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "figshare",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "figshare-search",
                "capability": "search",
                "export": "FigshareSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "figshare-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.figshare.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["figshare-provider-config-v1"],
        },
    }
)

__all__ = ["FIGSHARE_PROVIDER_MANIFEST"]
