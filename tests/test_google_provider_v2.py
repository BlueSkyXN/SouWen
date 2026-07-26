from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.google import (
    GOOGLE_PROVIDER_MANIFEST,
    GOOGLE_PROVIDER_SPEC,
)


def test_google_spec_matches_manifest():
    validate_spec_manifest(GOOGLE_PROVIDER_SPEC, GOOGLE_PROVIDER_MANIFEST)
