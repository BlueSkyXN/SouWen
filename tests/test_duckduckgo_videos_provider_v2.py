from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.duckduckgo_videos import (
    DUCKDUCKGO_VIDEOS_PROVIDER_MANIFEST,
    DUCKDUCKGO_VIDEOS_PROVIDER_SPEC,
)


def test_duckduckgo_videos_spec_matches_manifest():
    validate_spec_manifest(DUCKDUCKGO_VIDEOS_PROVIDER_SPEC, DUCKDUCKGO_VIDEOS_PROVIDER_MANIFEST)
