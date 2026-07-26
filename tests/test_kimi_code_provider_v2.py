from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.kimi_code import (
    KIMI_CODE_FETCH_PROVIDER_SPEC,
    KIMI_CODE_PROVIDER_MANIFEST,
    KIMI_CODE_SEARCH_PROVIDER_SPEC,
)


def test_kimi_code_manifest_specs():
    assert (
        validate_spec_manifest(KIMI_CODE_SEARCH_PROVIDER_SPEC, KIMI_CODE_PROVIDER_MANIFEST)
        is KIMI_CODE_SEARCH_PROVIDER_SPEC
    )
    assert (
        validate_spec_manifest(KIMI_CODE_FETCH_PROVIDER_SPEC, KIMI_CODE_PROVIDER_MANIFEST)
        is KIMI_CODE_FETCH_PROVIDER_SPEC
    )
