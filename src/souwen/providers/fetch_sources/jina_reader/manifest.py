"""Static Provider v2 declaration for Jina Reader Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

JINA_READER_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "jina_reader",
        "version": "2.0.0rc4",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "jina-reader-fetch",
                "capability": "fetch",
                "export": "JinaReaderFetchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "jina-reader-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["JINA_API_KEY"]},
        "network": {
            "egress_hosts": ["r.jina.ai"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["jina-reader-provider-config-v1"],
        },
    }
)

__all__ = ["JINA_READER_PROVIDER_MANIFEST"]
