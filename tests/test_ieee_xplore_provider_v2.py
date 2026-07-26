from souwen.providers.information_sources.ieee_xplore import (
    IEEE_XPLORE_PROVIDER_MANIFEST,
    IEEE_XPLORE_PROVIDER_SPEC,
)


def test_ieee_xplore_provider_v2_declares_required_query_secret() -> None:
    assert IEEE_XPLORE_PROVIDER_SPEC.auth.field_name == "apikey"
    assert IEEE_XPLORE_PROVIDER_SPEC.auth.required is True
    assert IEEE_XPLORE_PROVIDER_MANIFEST.secrets.references == ("IEEE_API_KEY",)
