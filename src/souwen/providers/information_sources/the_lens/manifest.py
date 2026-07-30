"""Static Provider v2 declaration for authenticated The Lens Search."""

from souwen.platform.manifest_registry import ProviderManifest


THE_LENS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "the_lens",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "the_lens-search",
                "capability": "search",
                "export": "TheLensSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "the-lens-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["LENS_API_TOKEN"]},
        "network": {
            "egress_hosts": ["api.lens.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["the-lens-provider-config-v1"],
        },
    }
)

__all__ = ["THE_LENS_PROVIDER_MANIFEST"]
