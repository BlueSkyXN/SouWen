"""Static Provider v2 manifest for arXiv."""

from souwen.platform.manifest_registry import ProviderManifest

ARXIV_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "arxiv",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "arxiv-search",
                "capability": "search",
                "export": "ArxivSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "arxiv-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["export.arxiv.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["arxiv-provider-config-v1"],
        },
    }
)
