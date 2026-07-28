"""Static Provider v2 declaration for Cloudflare Browser Rendering Fetch."""

from souwen.platform.manifest_registry import ProviderManifest

CLOUDFLARE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "cloudflare",
        "version": "2.0.0rc3",
        "contract_version": "provider-v2",
        "capabilities": ["fetch"],
        "adapters": [
            {
                "id": "cloudflare-fetch",
                "capability": "fetch",
                "export": "CloudflareFetchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "cloudflare-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]},
        "network": {
            "egress_hosts": ["api.cloudflare.com"],
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": True, "costed": True},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["cloudflare-provider-config-v1"],
        },
    }
)

__all__ = ["CLOUDFLARE_PROVIDER_MANIFEST"]
