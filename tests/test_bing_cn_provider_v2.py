from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.bing_cn import (
    BING_CN_PROVIDER_MANIFEST,
    BING_CN_PROVIDER_SPEC,
)


def test_bing_cn_spec_matches_manifest():
    validate_spec_manifest(BING_CN_PROVIDER_SPEC, BING_CN_PROVIDER_MANIFEST)
