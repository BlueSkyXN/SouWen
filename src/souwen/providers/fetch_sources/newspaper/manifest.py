from souwen.platform.manifest_registry import ProviderManifest


NEWSPAPER_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "newspaper",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "newspaper-fetch",
                "capability": "fetch",
                "export": "NewspaperFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "newspaper-provider-config-v1",
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
            "config_schema_versions": ["newspaper-provider-config-v1"],
        },
    }
)

__all__ = ["NEWSPAPER_PROVIDER_MANIFEST"]
