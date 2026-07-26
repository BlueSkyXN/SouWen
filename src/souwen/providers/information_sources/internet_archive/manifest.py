"""Static Provider v2 manifest for anonymous Internet Archive search."""

from souwen.platform.manifest_registry import ProviderManifest

INTERNET_ARCHIVE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "internet_archive",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "internet_archive-search",
                "capability": "search",
                "export": "InternetArchiveSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "internet-archive-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["archive.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["internet-archive-provider-config-v1"],
        },
    }
)
__all__ = ["INTERNET_ARCHIVE_PROVIDER_MANIFEST"]
