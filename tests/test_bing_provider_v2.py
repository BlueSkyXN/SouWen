from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.bing import BING_PROVIDER_MANIFEST, BING_PROVIDER_SPEC


def test_bing_spec_matches_manifest():
    validate_spec_manifest(BING_PROVIDER_SPEC, BING_PROVIDER_MANIFEST)
