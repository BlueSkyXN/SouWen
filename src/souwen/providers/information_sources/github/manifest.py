"""Static Provider v2 manifest for github."""

from souwen.platform.manifest_registry import ProviderManifest

GITHUB_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "github",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "github-search",
                "capability": "search",
                "export": "GitHubSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "github-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["GITHUB_TOKEN"]},
        "network": {
            "egress_hosts": ["api.github.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["github-provider-config-v1"],
        },
    }
)
