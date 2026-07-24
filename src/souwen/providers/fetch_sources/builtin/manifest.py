"""Static Provider v2 declaration for target-native builtin Fetch."""

from souwen.platform.manifest_registry import ProviderManifest


BUILTIN_FETCH_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "builtin-fetch",
        "version": "2.0.0rc2",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "builtin-fetch",
                "capability": "fetch",
                "export": "BuiltinFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "builtin-fetch-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        # Targets are request-specific and validated before every connection.
        "network": {"egress_hosts": [], "proxy_supported": True, "browser_required": False},
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["builtin-fetch-provider-config-v1"],
        },
    }
)


__all__ = ["BUILTIN_FETCH_MANIFEST"]
