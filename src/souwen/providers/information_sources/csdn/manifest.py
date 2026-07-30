from souwen.platform.manifest_registry import ProviderManifest

CSDN_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "csdn",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "csdn-search",
                "capability": "search",
                "export": "CSDNSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "csdn-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["so.csdn.net"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["csdn-provider-config-v1"],
        },
    }
)
__all__ = ["CSDN_PROVIDER_MANIFEST"]
