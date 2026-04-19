"""SouWen 数据源注册表

文件用途：
    集中管理所有已知数据源的元数据（名称、分类、Tier、配置字段等），
    供配置验证、健康检查和 UI 使用。数据源分类：论文、专利、网页搜索。

函数/类清单：
    SourceMeta（dataclass）
        - 功能：数据源元数据容器
        - 属性：name (str) 源名称, category (str) 分类(paper|patent|web),
                tier (int) Tier(0=免配置/1=免费Key或自建/2=付费),
                config_field (str|None) 配置字段名, is_scraper (bool) 是否爬虫,
                description (str) 描述文本

    _reg(name, category, tier, config_field, *, is_scraper=False, description="")
        - 功能：向注册表添加单个数据源
        - 入参：name 源名称, category 分类, tier 付费层级, config_field 配置字段,
                is_scraper 爬虫标志, description 描述

    get_all_sources() -> dict[str, SourceMeta]
        - 功能：返回所有已注册数据源字典

    get_source(name: str) -> SourceMeta | None
        - 功能：按名称获取单个数据源元数据

    is_known_source(name: str) -> bool
        - 功能：检查是否是已知数据源名称

    get_scraper_sources() -> list[str]
        - 功能：返回所有爬虫类数据源名称列表

    get_sources_by_category(category: str) -> list[SourceMeta]
        - 功能：按分类（paper|patent|web）筛选数据源

    ALL_SOURCE_NAMES: frozenset[str]
        - 功能：所有源名称的不可变集合（常量）

模块依赖：
    - dataclasses: frozenset 容器定义
    - 无外部依赖
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据（不可变）

    每个数据源的注册信息，用于配置验证和 UI 展示。

    属性：
        name: 数据源唯一标识（如 'openalex'、'tavily'）
        category: 分类标签 — 'paper'（论文）| 'patent'（专利）| 'web'（网页搜索）
        tier: 付费层级 —
              0 = 免配置或完全免费（无需 API Key）
              1 = 免费 API 配额或自建服务
              2 = 付费 API 或专业付费版本
        config_field: 对应 SouWenConfig 中的字段名（如 'tavily_api_key'），
                      None 表示该源无需配置
        is_scraper: 是否使用 BaseScraper（受 curl_cffi TLS 指纹影响），
                    爬虫类源需要 curl_cffi 支持
        description: 用户可读的源描述（用于 UI 和文档）
    """

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
    """向全局注册表添加单个数据源

    Args:
        name: 数据源名称
        category: 分类（paper|patent|web）
        tier: Tier 级别（0|1|2）
        config_field: 配置字段名，None 表示无需配置
        is_scraper: 是否爬虫类源
        description: 用户描述文本
    """
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

# ── 网页搜索：社交/平台 ──────────────────────────────────
_reg("github", "web", 0, "github_token", description="GitHub 仓库搜索 (可选 Token)")
_reg("stackoverflow", "web", 0, "stackoverflow_api_key", description="StackOverflow 问答搜索")
_reg("reddit", "web", 0, None, description="Reddit 帖子搜索")
_reg("bilibili", "web", 0, None, is_scraper=True, description="Bilibili 视频搜索")

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
    """返回所有已注册数据源的字典

    Returns:
        {源名称: SourceMeta} 映射字典
    """
    return dict(_REGISTRY)


def get_source(name: str) -> SourceMeta | None:
    """按名称获取单个数据源的元数据

    Args:
        name: 数据源名称

    Returns:
        SourceMeta 对象，不存在则返回 None
    """
    return _REGISTRY.get(name)


def is_known_source(name: str) -> bool:
    """检查是否是已知数据源名称

    Args:
        name: 数据源名称

    Returns:
        True 表示该源已注册，False 表示未知源
    """
    return name in _REGISTRY


def get_scraper_sources() -> list[str]:
    """返回所有爬虫类数据源的名称列表

    爬虫类源使用 BaseScraper，需要 curl_cffi TLS 指纹支持。

    Returns:
        爬虫源名称列表
    """
    return [name for name, meta in _REGISTRY.items() if meta.is_scraper]


def get_sources_by_category(category: str) -> list[SourceMeta]:
    """按分类筛选数据源

    Args:
        category: 分类标签 — 'paper' | 'patent' | 'web'

    Returns:
        该分类下的 SourceMeta 对象列表
    """
    return [meta for meta in _REGISTRY.values() if meta.category == category]


ALL_SOURCE_NAMES: frozenset[str] = frozenset(_REGISTRY.keys())
