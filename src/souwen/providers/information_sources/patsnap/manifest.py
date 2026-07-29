"""Static Provider v2 declaration for authenticated PatSnap Search."""

from souwen.platform.manifest_registry import ProviderManifest


PATSNAP_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "patsnap",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "patsnap-search",
                "capability": "search",
                "export": "PatSnapSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "patsnap-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["PATSNAP_API_KEY"]},
        "network": {
            "egress_hosts": ["connect.patsnap.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["patsnap-provider-config-v1"],
        },
    }
)

__all__ = ["PATSNAP_PROVIDER_MANIFEST"]
