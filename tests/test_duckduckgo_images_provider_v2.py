from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.duckduckgo_images import (
    DUCKDUCKGO_IMAGES_PROVIDER_MANIFEST,
    DUCKDUCKGO_IMAGES_PROVIDER_SPEC,
)


def test_duckduckgo_images_spec_matches_manifest():
    validate_spec_manifest(DUCKDUCKGO_IMAGES_PROVIDER_SPEC, DUCKDUCKGO_IMAGES_PROVIDER_MANIFEST)
