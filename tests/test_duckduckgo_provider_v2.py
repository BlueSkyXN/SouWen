from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.duckduckgo import (
    DUCKDUCKGO_PROVIDER_MANIFEST,
    DUCKDUCKGO_PROVIDER_SPEC,
)


def test_duckduckgo_spec_matches_manifest():
    validate_spec_manifest(DUCKDUCKGO_PROVIDER_SPEC, DUCKDUCKGO_PROVIDER_MANIFEST)
