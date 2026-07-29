"""Static Provider v2 manifest for OpenAIRE."""

from souwen.platform.manifest_registry import ProviderManifest

OPENAIRE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "openaire",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "openaire-search",
                "capability": "search",
                "export": "OpenAireSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "openaire-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["OPENAIRE_API_KEY"]},
        "network": {
            "egress_hosts": ["api.openaire.eu"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["openaire-provider-config-v1"],
        },
    }
)
