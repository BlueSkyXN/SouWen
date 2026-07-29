"""Static Provider v2 declaration for authenticated CNIPA Search."""

from souwen.platform.manifest_registry import ProviderManifest


CNIPA_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "cnipa",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "cnipa-search",
                "capability": "search",
                "export": "CnipaSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "cnipa-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["CNIPA_CLIENT_ID", "CNIPA_CLIENT_SECRET"]},
        "network": {
            "egress_hosts": ["open.cnipr.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["cnipa-provider-config-v1"],
        },
    }
)

__all__ = ["CNIPA_PROVIDER_MANIFEST"]
