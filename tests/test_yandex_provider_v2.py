from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.yandex import (
    YANDEX_PROVIDER_MANIFEST,
    YANDEX_PROVIDER_SPEC,
)


def test_yandex_spec_matches_manifest():
    validate_spec_manifest(YANDEX_PROVIDER_SPEC, YANDEX_PROVIDER_MANIFEST)
