from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.firecrawl import (
    FIRECRAWL_FETCH_PROVIDER_SPEC,
    FIRECRAWL_PROVIDER_MANIFEST,
    FIRECRAWL_SEARCH_PROVIDER_SPEC,
)


def test_firecrawl_manifest_specs():
    assert (
        validate_spec_manifest(FIRECRAWL_SEARCH_PROVIDER_SPEC, FIRECRAWL_PROVIDER_MANIFEST)
        is FIRECRAWL_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(FIRECRAWL_FETCH_PROVIDER_SPEC, FIRECRAWL_PROVIDER_MANIFEST)
        is FIRECRAWL_FETCH_PROVIDER_SPEC
    )
