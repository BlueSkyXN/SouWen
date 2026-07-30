from souwen.platform.manifest_registry import ProviderManifest

YOUTUBE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "youtube",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "youtube-search",
                "capability": "search",
                "export": "YouTubeSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "youtube-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["YOUTUBE_API_KEY"]},
        "network": {
            "egress_hosts": ["www.googleapis.com"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["youtube-provider-config-v1"],
        },
    }
)
