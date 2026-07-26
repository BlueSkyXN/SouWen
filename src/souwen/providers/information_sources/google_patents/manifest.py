"""Static Provider v2 declaration for Google Patents Search."""

from souwen.platform.manifest_registry import ProviderManifest


GOOGLE_PATENTS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "google_patents",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "google_patents-search",
                "capability": "search",
                "export": "GooglePatentsSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "google-patents-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["patents.google.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["google-patents-provider-config-v1"],
        },
    }
)

__all__ = ["GOOGLE_PATENTS_PROVIDER_MANIFEST"]
