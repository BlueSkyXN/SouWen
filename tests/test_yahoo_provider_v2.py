from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.yahoo import YAHOO_PROVIDER_MANIFEST, YAHOO_PROVIDER_SPEC


def test_yahoo_spec_matches_manifest():
    validate_spec_manifest(YAHOO_PROVIDER_SPEC, YAHOO_PROVIDER_MANIFEST)
