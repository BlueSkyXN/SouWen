from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.metaso import (
    METASO_FETCH_PROVIDER_SPEC,
    METASO_PROVIDER_MANIFEST,
    METASO_SEARCH_PROVIDER_SPEC,
)


def test_metaso_manifest_specs():
    assert (
        validate_spec_manifest(METASO_SEARCH_PROVIDER_SPEC, METASO_PROVIDER_MANIFEST)
        is METASO_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(METASO_FETCH_PROVIDER_SPEC, METASO_PROVIDER_MANIFEST)
        is METASO_FETCH_PROVIDER_SPEC
    )
