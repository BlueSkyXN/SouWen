from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.baidu import BAIDU_PROVIDER_MANIFEST, BAIDU_PROVIDER_SPEC


def test_baidu_spec_matches_manifest():
    validate_spec_manifest(BAIDU_PROVIDER_SPEC, BAIDU_PROVIDER_MANIFEST)
