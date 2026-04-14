"""SouWen 数据源注册表

集中管理所有已知数据源的元数据，供配置验证、健康检查和 UI 使用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据"""

    name: str
    category: str  # paper | patent | web
    tier: int  # 0=免配置, 1=免费Key/自建, 2=付费
    config_field: str | None  # 对应 SouWenConfig 字段名
    is_scraper: bool  # 是否使用 BaseScraper (受 http_backend 影响)
    description: str


# 完整数据源注册表
_REGISTRY: dict[str, SourceMeta] = {}


def _reg(
    name: str,
    category: str,
    tier: int,
    config_field: str | None,
    *,
    is_scraper: bool = False,
    description: str = "",
) -> None:
    _REGISTRY[name] = SourceMeta(
        name=name,
        category=category,
        tier=tier,
        config_field=config_field,
        is_scraper=is_scraper,
        description=description,
    )


# ── 论文 ──────────────────────────────────────────────────
_reg("openalex", "paper", 0, "openalex_email", description="OpenAlex 开放学术数据")
_reg("semantic_scholar", "paper", 1, "semantic_scholar_api_key", description="Semantic Scholar API")
_reg("crossref", "paper", 0, None, description="CrossRef 跨库检索")
_reg("arxiv", "paper", 0, None, description="arXiv 预印本")
_reg("dblp", "paper", 0, None, description="DBLP 计算机科学文献")
_reg("core", "paper", 1, "core_api_key", description="CORE 开放获取聚合")
_reg("pubmed", "paper", 0, None, description="PubMed 生物医学")
_reg("unpaywall", "paper", 1, "unpaywall_email", description="Unpaywall OA 查找")

# ── 专利 ──────────────────────────────────────────────────
_reg("patentsview", "patent", 0, None, description="PatentsView 美国专利 (待修复)")
_reg("pqai", "patent", 0, None, description="PQAI 专利语义搜索 (待修复)")
_reg("epo_ops", "patent", 2, "epo_consumer_key", description="EPO OPS 欧洲专利局")
_reg("uspto_odp", "patent", 2, "uspto_api_key", description="USPTO ODP 美国专利局")
_reg("the_lens", "patent", 2, "lens_api_token", description="The Lens 专利+学术")
_reg("cnipa", "patent", 2, "cnipa_client_id", description="CNIPA 中国国知局")
_reg("patsnap", "patent", 2, "patsnap_api_key", description="PatSnap 智慧芽")
_reg("google_patents", "patent", 0, None, is_scraper=True, description="Google Patents 爬虫")

# ── 网页搜索：爬虫 ────────────────────────────────────────
_reg("duckduckgo", "web", 0, None, is_scraper=True, description="DuckDuckGo HTML 搜索")
_reg("yahoo", "web", 0, None, is_scraper=True, description="Yahoo 搜索")
_reg("brave", "web", 0, None, is_scraper=True, description="Brave 搜索")
_reg("google", "web", 0, None, is_scraper=True, description="Google 搜索")
_reg("bing", "web", 0, None, is_scraper=True, description="Bing 搜索")
_reg("startpage", "web", 0, None, is_scraper=True, description="Startpage 隐私搜索")
_reg("baidu", "web", 0, None, is_scraper=True, description="百度搜索")
_reg("mojeek", "web", 0, None, is_scraper=True, description="Mojeek 独立搜索")
_reg("yandex", "web", 0, None, is_scraper=True, description="Yandex 搜索")

# ── 网页搜索：自建 ────────────────────────────────────────
_reg("searxng", "web", 1, "searxng_url", description="SearXNG 元搜索 (自建)")
_reg("whoogle", "web", 1, "whoogle_url", description="Whoogle Google 代理 (自建)")
_reg("websurfx", "web", 1, "websurfx_url", description="Websurfx 聚合搜索 (自建)")

# ── 网页搜索：付费 API ────────────────────────────────────
_reg("tavily", "web", 2, "tavily_api_key", description="Tavily AI 搜索")
_reg("exa", "web", 2, "exa_api_key", description="Exa 语义搜索")
_reg("serper", "web", 2, "serper_api_key", description="Serper Google SERP")
_reg("brave_api", "web", 2, "brave_api_key", description="Brave Search API")
_reg("serpapi", "web", 2, "serpapi_api_key", description="SerpAPI 多引擎 SERP")
_reg("firecrawl", "web", 2, "firecrawl_api_key", description="Firecrawl 搜索+爬取")
_reg("perplexity", "web", 2, "perplexity_api_key", description="Perplexity Sonar AI")
_reg("linkup", "web", 2, "linkup_api_key", description="Linkup 实时搜索")
_reg("scrapingdog", "web", 2, "scrapingdog_api_key", description="ScrapingDog SERP")


# ── 公开 API ──────────────────────────────────────────────


def get_all_sources() -> dict[str, SourceMeta]:
    """返回所有已注册数据源"""
    return dict(_REGISTRY)


def get_source(name: str) -> SourceMeta | None:
    """按名称获取数据源元数据"""
    return _REGISTRY.get(name)


def is_known_source(name: str) -> bool:
    """检查是否是已知数据源名称"""
    return name in _REGISTRY


def get_scraper_sources() -> list[str]:
    """返回所有使用 BaseScraper 的数据源名称"""
    return [name for name, meta in _REGISTRY.items() if meta.is_scraper]


def get_sources_by_category(category: str) -> list[SourceMeta]:
    """按类别筛选数据源"""
    return [meta for meta in _REGISTRY.values() if meta.category == category]


ALL_SOURCE_NAMES: frozenset[str] = frozenset(_REGISTRY.keys())
