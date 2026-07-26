from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.mojeek import (
    MOJEEK_PROVIDER_MANIFEST,
    MOJEEK_PROVIDER_SPEC,
)


def test_mojeek_spec_matches_manifest():
    validate_spec_manifest(MOJEEK_PROVIDER_SPEC, MOJEEK_PROVIDER_MANIFEST)
