"""Static Provider v2 declaration for the authenticated PatentsView Search API."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest


PATENTSVIEW_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "patentsview",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "patentsview-search",
                "capability": "search",
                "export": "PatentsViewSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "patentsview-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "max_retries", "timeout_seconds"],
        },
        "secrets": {"references": ["PATENTSVIEW_API_KEY"]},
        "network": {
            "egress_hosts": ["search.patentsview.org"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["patentsview-provider-config-v1"],
        },
    }
)


__all__ = ["PATENTSVIEW_PROVIDER_MANIFEST"]
