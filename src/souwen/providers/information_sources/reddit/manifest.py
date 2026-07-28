"""Static Provider v2 manifest for reddit."""

from souwen.platform.manifest_registry import ProviderManifest

REDDIT_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "reddit",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "reddit-search",
                "capability": "search",
                "export": "RedditSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "reddit-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {
            "references": [],
            "optional_references": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
        },
        "network": {
            "egress_hosts": ["www.reddit.com", "oauth.reddit.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["reddit-provider-config-v1"],
        },
    }
)
