from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.bilibili import (
    BILIBILI_PROVIDER_MANIFEST,
    BILIBILI_PROVIDER_SPEC,
)
from souwen.providers.information_sources.bilibili.adapter import build_bilibili_client


def test_bilibili_spec_matches_manifest():
    validate_spec_manifest(BILIBILI_PROVIDER_SPEC, BILIBILI_PROVIDER_MANIFEST)


def test_bilibili_factory_injects_optional_secret_without_global_config():
    client = build_bilibili_client({}, {"BILIBILI_SESSDATA": "test-session"})
    assert client._sessdata == "test-session"
    assert client._follow_redirects is False
