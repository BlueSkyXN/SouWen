from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.duckduckgo_news import (
    DUCKDUCKGO_NEWS_PROVIDER_MANIFEST,
    DUCKDUCKGO_NEWS_PROVIDER_SPEC,
)


def test_duckduckgo_news_spec_matches_manifest():
    validate_spec_manifest(DUCKDUCKGO_NEWS_PROVIDER_SPEC, DUCKDUCKGO_NEWS_PROVIDER_MANIFEST)
