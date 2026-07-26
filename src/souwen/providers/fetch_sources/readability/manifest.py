from souwen.platform.manifest_registry import ProviderManifest


READABILITY_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "readability",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "readability-fetch",
                "capability": "fetch",
                "export": "ReadabilityFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "readability-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": [],
            "target_egress": "validated_public_target",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["readability-provider-config-v1"],
        },
    }
)

__all__ = ["READABILITY_PROVIDER_MANIFEST"]
