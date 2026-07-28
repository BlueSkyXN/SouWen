"""Static Provider v2 manifest for anonymous Library of Congress search."""

from souwen.platform.manifest_registry import ProviderManifest

LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "library_of_congress",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "library_of_congress-search",
                "capability": "search",
                "export": "LibraryOfCongressSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "library-of-congress-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["www.loc.gov"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["library-of-congress-provider-config-v1"],
        },
    }
)
__all__ = ["LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST"]
