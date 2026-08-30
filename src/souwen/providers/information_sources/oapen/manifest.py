"""Static Provider v2 manifest for anonymous OAPEN search."""

from souwen.platform.manifest_registry import ProviderManifest

OAPEN_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "oapen",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "oapen-search",
                "capability": "search",
                "export": "OAPENSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "oapen-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["library.oapen.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["oapen-provider-config-v1"],
        },
    }
)
__all__ = ["OAPEN_PROVIDER_MANIFEST"]
