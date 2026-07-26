from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.startpage import (
    STARTPAGE_PROVIDER_MANIFEST,
    STARTPAGE_PROVIDER_SPEC,
)


def test_startpage_spec_matches_manifest():
    validate_spec_manifest(STARTPAGE_PROVIDER_SPEC, STARTPAGE_PROVIDER_MANIFEST)
