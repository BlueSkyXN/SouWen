"""Static Provider v2 declaration for the anonymous ERIC search API."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest


ERIC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "eric",
        "version": "2.0.0rc5",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "eric-search",
                "capability": "search",
                "export": "EricSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "eric-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "max_retries", "timeout_seconds"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.ies.ed.gov"],
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["eric-provider-config-v1"],
        },
    }
)


__all__ = ["ERIC_PROVIDER_MANIFEST"]
