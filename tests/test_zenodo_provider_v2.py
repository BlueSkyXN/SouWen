from souwen.providers.information_sources.zenodo import (
    ZENODO_PROVIDER_MANIFEST,
    ZENODO_PROVIDER_SPEC,
)


def test_zenodo_provider_v2_declares_optional_bearer_secret() -> None:
    assert ZENODO_PROVIDER_SPEC.auth.reference == "ZENODO_ACCESS_TOKEN"
    assert ZENODO_PROVIDER_SPEC.auth.required is False
    assert ZENODO_PROVIDER_MANIFEST.secrets.optional_references == ("ZENODO_ACCESS_TOKEN",)
