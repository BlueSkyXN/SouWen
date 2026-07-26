from souwen.providers.information_sources.doaj import DOAJ_PROVIDER_MANIFEST, DOAJ_PROVIDER_SPEC


def test_doaj_provider_v2_declares_optional_header_secret() -> None:
    assert DOAJ_PROVIDER_SPEC.auth.reference == "DOAJ_API_KEY"
    assert DOAJ_PROVIDER_SPEC.auth.required is False
    assert DOAJ_PROVIDER_MANIFEST.secrets.optional_references == ("DOAJ_API_KEY",)
