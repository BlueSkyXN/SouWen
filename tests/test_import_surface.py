"""v2 public import surface tests."""

import importlib
import pytest


def test_new_public_import_surface():
    """Root public entry is limited to the generated target SDK."""
    import souwen

    from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
    from souwen.common_runtime.provider_support.scraper.base import BaseScraper
    from souwen.providers.runtime_clients.local_catalog import LocalCatalog
    from souwen.providers.runtime_clients.web.fetch import validate_fetch_url
    from souwen.providers.runtime_clients.web.wayback import WaybackClient
    from souwen import AsyncSouWenClient, SouWenClient

    assert set(souwen.__all__) == {"__version__", "SouWenClient", "AsyncSouWenClient"}
    assert callable(validate_fetch_url)
    assert SouWenHttpClient.__name__ == "SouWenHttpClient"
    assert BaseScraper.__name__ == "BaseScraper"
    assert WaybackClient.__name__ == "WaybackClient"
    assert LocalCatalog.__name__ == "LocalCatalog"
    assert SouWenClient.__name__ == "SouWenClient"
    assert AsyncSouWenClient.__name__ == "AsyncSouWenClient"


@pytest.mark.parametrize(
    "name",
    [
        "souwen.registry",
        "souwen.core",
        "souwen.paper",
        "souwen.patent",
        "souwen.web",
        "souwen.book",
        "souwen.research_output",
        "souwen.local_catalog",
        "souwen.llm",
        "souwen.search",
        "souwen.models",
        "souwen.citations",
        "souwen.doctor",
        "souwen.provenance",
        "souwen.wikisource",
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
        "souwen.providers.runtime_clients.web.engines",
        "souwen.providers.runtime_clients.web.api",
        "souwen.providers.runtime_clients.web.self_hosted",
    ],
)
def test_removed_import_surface(name):
    """V1 兼容路径在 V2 中必须不可 import。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)
