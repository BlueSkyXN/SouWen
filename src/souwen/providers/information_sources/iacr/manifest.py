"""Static Provider v2 declaration for IACR ePrint Search."""

from souwen.platform.manifest_registry import ProviderManifest


IACR_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "iacr",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "iacr-search",
                "capability": "search",
                "export": "IacrSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "iacr-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["eprint.iacr.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["iacr-provider-config-v1"],
        },
    }
)

__all__ = ["IACR_PROVIDER_MANIFEST"]
