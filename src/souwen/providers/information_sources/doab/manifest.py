"""Static Provider v2 manifest for anonymous DOAB search."""

from souwen.platform.manifest_registry import ProviderManifest

DOAB_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "doab",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "doab-search",
                "capability": "search",
                "export": "DOABSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "doab-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["directory.doabooks.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["doab-provider-config-v1"],
        },
    }
)
__all__ = ["DOAB_PROVIDER_MANIFEST"]
