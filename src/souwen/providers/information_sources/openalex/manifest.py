"""Static Provider v2 declaration for the built-in OpenAlex search adapter."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest


OPENALEX_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "openalex",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "openalex-search",
                "capability": "search",
                "export": "OpenAlexSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "openalex-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        # OpenAlex has anonymous access. An API key raises quota but is not a
        # required v2 secret reference and therefore cannot make it ineligible.
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.openalex.org"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["openalex-provider-config-v1"],
        },
    }
)


__all__ = ["OPENALEX_PROVIDER_MANIFEST"]
