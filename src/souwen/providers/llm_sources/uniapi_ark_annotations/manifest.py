"""Static manifests for the two immutable target UniAPI Ark adapters."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest


DEEPSEEK_ADAPTER_ID = "uniapi_ark_annotations_deepseek_v3_2_251201"
DOUBAO_ADAPTER_ID = "uniapi_ark_annotations_doubao_seed_2_0_lite_260428"


def _manifest(adapter_id: str, export: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "schema_version": 2,
            "id": adapter_id,
            "version": "2.0.0rc3",
            "contract_version": "provider-v2",
            "capabilities": ["llm_search"],
            "adapters": [
                {
                    "id": adapter_id,
                    "capability": "llm_search",
                    "export": export,
                    "availability": "configured",
                }
            ],
            "configuration": {
                "schema_reference": "uniapi-ark-provider-config-v1",
                "unknown_key_policy": "reject",
                "non_secret_keys": ["enabled", "max_keyword", "timeout_seconds"],
            },
            "secrets": {"references": ["UNIAPI_API_KEY", "UNIAPI_BASE_URL"]},
            # The gateway host is deployment-owned and may be private. It is
            # deliberately absent from public static catalog metadata.
            "network": {
                "egress_hosts": [],
                "proxy_supported": False,
                "browser_required": False,
            },
            "risk": {"authenticated": True, "costed": True},
            "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
            "compatibility": {
                "contract_versions": ["provider-v2"],
                "config_schema_versions": ["uniapi-ark-provider-config-v1"],
            },
        }
    )


UNIAPI_ARK_DEEPSEEK_MANIFEST = _manifest(
    DEEPSEEK_ADAPTER_ID,
    "UniApiArkAnnotationsDeepSeekProvider",
)
UNIAPI_ARK_DOUBAO_MANIFEST = _manifest(
    DOUBAO_ADAPTER_ID,
    "UniApiArkAnnotationsDoubaoProvider",
)
UNIAPI_ARK_MANIFESTS = (UNIAPI_ARK_DEEPSEEK_MANIFEST, UNIAPI_ARK_DOUBAO_MANIFEST)


__all__ = [
    "DEEPSEEK_ADAPTER_ID",
    "DOUBAO_ADAPTER_ID",
    "UNIAPI_ARK_DEEPSEEK_MANIFEST",
    "UNIAPI_ARK_DOUBAO_MANIFEST",
    "UNIAPI_ARK_MANIFESTS",
]
