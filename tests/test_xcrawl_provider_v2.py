from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.xcrawl import (
    XCRAWL_FETCH_PROVIDER_SPEC,
    XCRAWL_PROVIDER_MANIFEST,
    XCRAWL_SEARCH_PROVIDER_SPEC,
)


def test_xcrawl_manifest_specs():
    assert (
        validate_spec_manifest(XCRAWL_SEARCH_PROVIDER_SPEC, XCRAWL_PROVIDER_MANIFEST)
        is XCRAWL_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(XCRAWL_FETCH_PROVIDER_SPEC, XCRAWL_PROVIDER_MANIFEST)
        is XCRAWL_FETCH_PROVIDER_SPEC
    )
