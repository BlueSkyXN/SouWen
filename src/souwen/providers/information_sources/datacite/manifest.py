"""Static Provider v2 manifest for anonymous DataCite metadata search."""

from souwen.platform.manifest_registry import ProviderManifest


DATACITE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "datacite",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "datacite-search",
                "capability": "search",
                "export": "DataCiteSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "datacite-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.datacite.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["datacite-provider-config-v1"],
        },
    }
)

__all__ = ["DATACITE_PROVIDER_MANIFEST"]
