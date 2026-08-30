"""Static Provider v2 declaration for anonymous OSTI Search."""

from souwen.platform.manifest_registry import ProviderManifest


OSTI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "osti",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "osti-search",
                "capability": "search",
                "export": "OstiSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "osti-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["www.osti.gov"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["osti-provider-config-v1"],
        },
    }
)

__all__ = ["OSTI_PROVIDER_MANIFEST"]
