from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.brave import BRAVE_PROVIDER_MANIFEST, BRAVE_PROVIDER_SPEC


def test_brave_spec_matches_manifest():
    validate_spec_manifest(BRAVE_PROVIDER_SPEC, BRAVE_PROVIDER_MANIFEST)
