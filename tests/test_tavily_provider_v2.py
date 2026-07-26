from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.tavily import (
    TAVILY_FETCH_PROVIDER_SPEC,
    TAVILY_PROVIDER_MANIFEST,
    TAVILY_SEARCH_PROVIDER_SPEC,
)


def test_tavily_manifest_specs():
    assert (
        validate_spec_manifest(TAVILY_SEARCH_PROVIDER_SPEC, TAVILY_PROVIDER_MANIFEST)
        is TAVILY_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(TAVILY_FETCH_PROVIDER_SPEC, TAVILY_PROVIDER_MANIFEST)
        is TAVILY_FETCH_PROVIDER_SPEC
    )
