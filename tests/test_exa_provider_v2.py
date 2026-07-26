from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.exa import (
    EXA_FETCH_PROVIDER_SPEC,
    EXA_PROVIDER_MANIFEST,
    EXA_SEARCH_PROVIDER_SPEC,
)


def test_exa_manifest_specs():
    assert (
        validate_spec_manifest(EXA_SEARCH_PROVIDER_SPEC, EXA_PROVIDER_MANIFEST)
        is EXA_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(EXA_FETCH_PROVIDER_SPEC, EXA_PROVIDER_MANIFEST)
        is EXA_FETCH_PROVIDER_SPEC
    )
