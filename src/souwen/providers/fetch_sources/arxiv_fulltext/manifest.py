"""Static Provider v2 declaration for source-specific arXiv full-text Fetch."""

from souwen.platform.manifest_registry import ProviderManifest


ARXIV_FULLTEXT_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "arxiv_fulltext",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "arxiv_fulltext-fetch",
                "capability": "fetch",
                "export": "ArxivFulltextFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "arxiv-fulltext-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["arxiv.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["arxiv-fulltext-provider-config-v1"],
        },
    }
)

__all__ = ["ARXIV_FULLTEXT_PROVIDER_MANIFEST"]
