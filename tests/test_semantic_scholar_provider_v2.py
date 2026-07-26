from souwen.providers.information_sources.semantic_scholar import (
    SEMANTIC_SCHOLAR_PROVIDER_MANIFEST,
    SEMANTIC_SCHOLAR_PROVIDER_SPEC,
)


def test_semantic_scholar_provider_v2_declares_optional_header_secret() -> None:
    assert SEMANTIC_SCHOLAR_PROVIDER_SPEC.auth.field_name == "x-api-key"
    assert SEMANTIC_SCHOLAR_PROVIDER_SPEC.auth.required is False
    assert SEMANTIC_SCHOLAR_PROVIDER_MANIFEST.secrets.optional_references == (
        "SEMANTIC_SCHOLAR_API_KEY",
    )
