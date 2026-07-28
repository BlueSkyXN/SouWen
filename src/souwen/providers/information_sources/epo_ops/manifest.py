"""Static Provider v2 declaration for authenticated EPO OPS Search."""

from souwen.platform.manifest_registry import ProviderManifest


EPO_OPS_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "epo_ops",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "epo_ops-search",
                "capability": "search",
                "export": "EpoOpsSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "epo-ops-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["EPO_CONSUMER_KEY", "EPO_CONSUMER_SECRET"]},
        "network": {
            "egress_hosts": ["ops.epo.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["epo-ops-provider-config-v1"],
        },
    }
)

__all__ = ["EPO_OPS_PROVIDER_MANIFEST"]
