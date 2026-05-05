"""v2 public import surface tests."""

import importlib

import pytest


def test_new_public_import_surface():
    """V2 公开入口只暴露真实模块路径。"""
    from souwen.core.http_client import SouWenHttpClient
    from souwen.core.scraper.base import BaseScraper
    from souwen.registry.meta import get_all_sources
    from souwen.search import search, search_all, search_by_capability, search_domain
    from souwen.web.fetch import fetch_content
    from souwen.web.wayback import WaybackClient

    assert callable(search)
    assert callable(search_all)
    assert callable(search_by_capability)
    assert callable(search_domain)
    assert callable(fetch_content)
    assert callable(get_all_sources)
    assert SouWenHttpClient.__name__ == "SouWenHttpClient"
    assert BaseScraper.__name__ == "BaseScraper"
    assert WaybackClient.__name__ == "WaybackClient"


@pytest.mark.parametrize(
    "name",
    [
        "souwen.facade",
        "souwen.source_registry",
        "souwen.exceptions",
        "souwen.http_client",
        "souwen.rate_limiter",
        "souwen._parsing",
        "souwen.retry",
        "souwen.fingerprint",
        "souwen.session_cache",
        "souwen.scraper",
        "souwen.scraper.base",
        "souwen.fetch",
        "souwen.fetch.providers",
        "souwen.cn_tech",
        "souwen.social",
        "souwen.video",
        "souwen.developer",
        "souwen.knowledge",
        "souwen.office",
        "souwen.archive",
        "souwen.web.engines",
        "souwen.web.api",
        "souwen.web.self_hosted",
    ],
)
def test_removed_import_surface(name):
    """V1 兼容路径在 V2 中必须不可 import。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)
