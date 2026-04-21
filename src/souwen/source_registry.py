"""SouWen 数据源注册表

文件用途：
    集中管理所有已知数据源的元数据（名称、分类、集成类型、配置字段等），
    供配置验证、健康检查和 UI 使用。

    数据源分类维度：
        category（内容分类）—— paper（论文）| patent（专利）| web（网页搜索）
        integration_type（集成类型）——
            open_api      公开接口：官方提供免费公开 API，无需 Key
            scraper       爬虫抓取：无官方 API，需爬虫 / 过盾抓取
            official_api  授权接口：官方 API，需 API Key 授权
            self_hosted   自托管：用户自建实例

函数/类清单：
    SourceMeta（dataclass）
        - 功能：数据源元数据容器
        - 属性：name (str), category (str), integration_type (str),
                config_field (str|None), description (str)

    _reg(name, category, integration_type, config_field, *, description="")
        - 功能：向注册表添加单个数据源

    get_all_sources() -> dict[str, SourceMeta]
    get_source(name: str) -> SourceMeta | None
    is_known_source(name: str) -> bool
    get_scraper_sources() -> list[str]
    get_sources_by_category(category: str) -> list[SourceMeta]
    get_sources_by_integration_type(integration_type: str) -> list[SourceMeta]
    ALL_SOURCE_NAMES: frozenset[str]

模块依赖：
    - dataclasses
    - 无外部依赖
"""

from __future__ import annotations

from dataclasses import dataclass

# 合法的 integration_type 值
INTEGRATION_TYPES = frozenset({"open_api", "scraper", "official_api", "self_hosted"})

# integration_type 的用户可读标签
INTEGRATION_TYPE_LABELS: dict[str, str] = {
    "open_api": "公开接口 — 免配置 / 官方开放 API",
    "scraper": "爬虫抓取 — 无官方 API / 需 TLS 伪装",
    "official_api": "授权接口 — 需 API Key",
    "self_hosted": "自托管 — 需自建服务实例",
}


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据（不可变）

    每个数据源的注册信息，用于配置验证和 UI 展示。

    属性：
        name: 数据源唯一标识（如 'openalex'、'tavily'）
        category: 内容分类 — 'paper'（论文）| 'patent'（专利）| 'web'（网页搜索）
        integration_type: 集成类型 —
              'open_api'     = 公开接口（官方免费 API，无需 Key）
              'scraper'      = 爬虫抓取（无官方 API，需爬虫/TLS 伪装）
              'official_api' = 授权接口（官方 API，需 API Key）
              'self_hosted'  = 自托管（用户自建实例）
        config_field: 对应 SouWenConfig 中的字段名（如 'tavily_api_key'），
                      None 表示该源无需配置
        description: 用户可读的源描述（用于 UI 和文档）
    """

    name: str
    category: str  # paper | patent | web
    integration_type: str  # open_api | scraper | official_api | self_hosted
    config_field: str | None  # 对应 SouWenConfig 字段名
    description: str

    @property
    def is_scraper(self) -> bool:
        """是否爬虫类源（需要 curl_cffi TLS 指纹支持）"""
        return self.integration_type == "scraper"


# 完整数据源注册表
_REGISTRY: dict[str, SourceMeta] = {}


def _reg(
    name: str,
    category: str,
    integration_type: str,
    config_field: str | None,
    *,
    description: str = "",
) -> None:
    """向全局注册表添加单个数据源

    Args:
        name: 数据源名称
        category: 内容分类（paper|patent|web）
        integration_type: 集成类型（open_api|scraper|official_api|self_hosted）
        config_field: 配置字段名，None 表示无需配置
        description: 用户描述文本
    """
    _REGISTRY[name] = SourceMeta(
        name=name,
        category=category,
        integration_type=integration_type,
        config_field=config_field,
        description=description,
    )


# ── 论文：公开接口 ────────────────────────────────────────
_reg("openalex", "paper", "open_api", "openalex_email", description="OpenAlex 开放学术数据")
_reg("crossref", "paper", "open_api", None, description="CrossRef 跨库检索")
_reg("arxiv", "paper", "open_api", None, description="arXiv 预印本")
_reg("dblp", "paper", "open_api", None, description="DBLP 计算机科学文献")
_reg("pubmed", "paper", "open_api", None, description="PubMed 生物医学")
_reg(
    "huggingface",
    "paper",
    "open_api",
    None,
    description="HuggingFace Papers 社区精选（语义搜索 + 热度排行，无需 Key）",
)
_reg("europepmc", "paper", "open_api", None, description="Europe PMC 欧洲生物医学文献")
_reg("pmc", "paper", "open_api", None, description="PubMed Central 生物医学全文")
_reg("hal", "paper", "open_api", None, description="HAL 法国开放档案（Solr API）")
_reg(
    "iacr",
    "paper",
    "scraper",
    None,
    description="IACR ePrint 密码学预印本（实验性 HTML 爬虫）",
)

# ── 论文：授权接口 ────────────────────────────────────────
_reg(
    "semantic_scholar",
    "paper",
    "official_api",
    "semantic_scholar_api_key",
    description="Semantic Scholar API",
)
_reg("core", "paper", "official_api", "core_api_key", description="CORE 开放获取聚合")
_reg("unpaywall", "paper", "official_api", "unpaywall_email", description="Unpaywall OA 查找")
_reg(
    "zotero",
    "paper",
    "official_api",
    "zotero_api_key",
    description="Zotero 个人文献库搜索 (需 API Key + Library ID)",
)
_reg(
    "doaj", "paper", "official_api", "doaj_api_key", description="DOAJ 开放获取期刊目录（可选 Key）"
)
_reg(
    "zenodo",
    "paper",
    "official_api",
    "zenodo_access_token",
    description="Zenodo CERN 开放科学仓库（可选 Token）",
)
_reg(
    "openaire",
    "paper",
    "official_api",
    "openaire_api_key",
    description="OpenAIRE 欧盟研究基础设施（可选 Key）",
)

# ── 专利：公开接口 ────────────────────────────────────────
_reg("patentsview", "patent", "open_api", None, description="PatentsView 美国专利 (待修复)")
_reg("pqai", "patent", "open_api", None, description="PQAI 专利语义搜索 (待修复)")

# ── 专利：授权接口 ────────────────────────────────────────
_reg("epo_ops", "patent", "official_api", "epo_consumer_key", description="EPO OPS 欧洲专利局")
_reg("uspto_odp", "patent", "official_api", "uspto_api_key", description="USPTO ODP 美国专利局")
_reg("the_lens", "patent", "official_api", "lens_api_token", description="The Lens 专利+学术")
_reg("cnipa", "patent", "official_api", "cnipa_client_id", description="CNIPA 中国国知局")
_reg("patsnap", "patent", "official_api", "patsnap_api_key", description="PatSnap 智慧芽")

# ── 专利：爬虫 ────────────────────────────────────────────
_reg("google_patents", "patent", "scraper", None, description="Google Patents 爬虫")

# ── 通用搜索 (general)：爬虫 ──────────────────────────────
_reg("duckduckgo", "general", "scraper", None, description="DuckDuckGo 网页搜索")
_reg("duckduckgo_news", "general", "scraper", None, description="DuckDuckGo 新闻搜索")
_reg("duckduckgo_images", "general", "scraper", None, description="DuckDuckGo 图片搜索")
_reg("duckduckgo_videos", "general", "scraper", None, description="DuckDuckGo 视频搜索")
_reg("yahoo", "general", "scraper", None, description="Yahoo 搜索")
_reg("brave", "general", "scraper", None, description="Brave 搜索")
_reg("google", "general", "scraper", None, description="Google 搜索")
_reg("bing", "general", "scraper", None, description="Bing 搜索")
_reg("bing_cn", "general", "scraper", None, description="必应中文搜索 (cn.bing.com)")
_reg("startpage", "general", "scraper", None, description="Startpage 隐私搜索")
_reg("baidu", "general", "scraper", None, description="百度搜索")
_reg("mojeek", "general", "scraper", None, description="Mojeek 独立搜索")
_reg("yandex", "general", "scraper", None, description="Yandex 搜索")

# ── 通用搜索 (general)：自托管 ────────────────────────────
_reg("searxng", "general", "self_hosted", "searxng_url", description="SearXNG 元搜索 (自建)")
_reg("whoogle", "general", "self_hosted", "whoogle_url", description="Whoogle Google 代理 (自建)")
_reg("websurfx", "general", "self_hosted", "websurfx_url", description="Websurfx 聚合搜索 (自建)")

# ── 通用搜索 (general)：授权接口 ──────────────────────────
_reg("serpapi", "general", "official_api", "serpapi_api_key", description="SerpAPI 多引擎 SERP")
_reg("brave_api", "general", "official_api", "brave_api_key", description="Brave Search API")
_reg("serper", "general", "official_api", "serper_api_key", description="Serper Google SERP")
_reg(
    "scrapingdog", "general", "official_api", "scrapingdog_api_key", description="ScrapingDog SERP"
)
_reg(
    "metaso",
    "general",
    "official_api",
    "metaso_api_key",
    description="Metaso 秘塔搜索 (文档/网页/学术)",
)

# ── 专业搜索 (professional)：授权接口 ────────────────────
_reg("tavily", "professional", "official_api", "tavily_api_key", description="Tavily AI 搜索")
_reg("exa", "professional", "official_api", "exa_api_key", description="Exa 语义搜索")
_reg(
    "perplexity",
    "professional",
    "official_api",
    "perplexity_api_key",
    description="Perplexity Sonar AI",
)
_reg(
    "firecrawl",
    "professional",
    "official_api",
    "firecrawl_api_key",
    description="Firecrawl 搜索+爬取",
)
_reg("linkup", "professional", "official_api", "linkup_api_key", description="Linkup 实时搜索")
_reg(
    "zhipuai",
    "professional",
    "official_api",
    "zhipuai_api_key",
    description="智谱 AI Web Search Pro",
)
_reg(
    "aliyun_iqs",
    "professional",
    "official_api",
    "aliyun_iqs_api_key",
    description="阿里云 IQS 通义晓搜",
)

# ── 社交 (social)：公开接口/爬虫 ─────────────────────────
_reg("reddit", "social", "open_api", None, description="Reddit 帖子搜索")
_reg(
    "twitter",
    "social",
    "official_api",
    "twitter_bearer_token",
    description="Twitter/X 推文搜索（API v2）",
)
_reg(
    "facebook",
    "social",
    "official_api",
    "facebook_app_id",
    description="Facebook 页面/地点搜索（Graph API）",
)
_reg("weibo", "social", "scraper", None, description="微博搜索")
_reg("zhihu", "social", "scraper", None, description="知乎问答搜索")

# ── 办公/企业 (office)：授权接口 ──────────────────────────
_reg(
    "feishu_drive",
    "office",
    "official_api",
    "feishu_app_id",
    description="飞书云文档搜索 (需 App ID + App Secret)",
)

# ── 中文技术社区 (cn_tech)：公开接口/爬虫 ─────────────────
_reg("csdn", "cn_tech", "scraper", None, description="CSDN 技术博客搜索")
_reg("juejin", "cn_tech", "scraper", None, description="稀土掘金技术文章搜索")
_reg("linuxdo", "cn_tech", "open_api", None, description="LinuxDo 论坛搜索（Discourse）")

# ── 开发 (developer)：公开接口 ───────────────────────────
_reg("github", "developer", "open_api", "github_token", description="GitHub 仓库搜索 (可选 Token)")
_reg(
    "stackoverflow",
    "developer",
    "open_api",
    "stackoverflow_api_key",
    description="StackOverflow 问答搜索",
)

# ── 百科 (wiki)：公开接口 ────────────────────────────────
_reg("wikipedia", "wiki", "open_api", None, description="Wikipedia 百科搜索")

# ── 视频 (video)：授权接口/爬虫 ──────────────────────────
_reg("youtube", "video", "official_api", "youtube_api_key", description="YouTube 视频搜索")
_reg(
    "bilibili",
    "video",
    "scraper",
    "bilibili_sessdata",
    description="Bilibili 搜索（视频/用户/专栏文章）+ 视频详情抓取",
)

# ── 内容抓取 (fetch)：内置/公开接口/授权接口 ──────────────
_reg(
    "builtin",
    "fetch",
    "scraper",
    None,
    description="内置抓取 (httpx/curl_cffi + trafilatura, 零配置)",
)
_reg(
    "jina_reader",
    "fetch",
    "open_api",
    "jina_api_key",
    description="Jina Reader 内容抓取 (免费, 可选 Key)",
)
# Note: tavily/firecrawl/exa 的 fetch 能力复用其搜索注册条目（同一 API Key）
_reg("crawl4ai", "fetch", "scraper", None, description="Crawl4AI 无头浏览器抓取 (本地)")
_reg(
    "scrapfly",
    "fetch",
    "official_api",
    "scrapfly_api_key",
    description="Scrapfly JS 渲染 + AI 抽取",
)
_reg("diffbot", "fetch", "official_api", "diffbot_api_token", description="Diffbot 结构化文章抽取")
_reg(
    "scrapingbee",
    "fetch",
    "official_api",
    "scrapingbee_api_key",
    description="ScrapingBee 代理 + JS 渲染",
)
_reg(
    "zenrows",
    "fetch",
    "official_api",
    "zenrows_api_key",
    description="ZenRows 代理 + JS 渲染 + 反爬",
)
_reg(
    "scraperapi",
    "fetch",
    "official_api",
    "scraperapi_api_key",
    description="ScraperAPI 代理池 + JS 渲染",
)
_reg("apify", "fetch", "official_api", "apify_api_token", description="Apify Actor 爬虫平台")
_reg(
    "cloudflare",
    "fetch",
    "official_api",
    "cloudflare_api_token",
    description="Cloudflare Browser Rendering",
)
_reg("wayback", "fetch", "open_api", None, description="Internet Archive Wayback (免费)")
_reg("newspaper", "fetch", "scraper", None, description="newspaper4k 文章抽取 (本地)")
_reg("readability", "fetch", "scraper", None, description="Mozilla Readability 算法 (本地)")
_reg("mcp", "fetch", "open_api", None, description="MCP 协议内容抓取 (外部工具)")
_reg("site_crawler", "fetch", "scraper", None, description="BFS 站点爬虫 (批量多页面)")
_reg("deepwiki", "fetch", "open_api", None, description="DeepWiki 开源项目文档抓取 (免费)")


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

    爬虫类源（integration_type == 'scraper'）使用 BaseScraper，
    需要 curl_cffi TLS 指纹支持。

    Returns:
        爬虫源名称列表
    """
    return [name for name, meta in _REGISTRY.items() if meta.is_scraper]


def get_sources_by_category(category: str) -> list[SourceMeta]:
    """按内容分类筛选数据源

    Args:
        category: 分类标签 — 'paper' | 'patent' | 'web'

    Returns:
        该分类下的 SourceMeta 对象列表
    """
    return [meta for meta in _REGISTRY.values() if meta.category == category]


def get_sources_by_integration_type(integration_type: str) -> list[SourceMeta]:
    """按集成类型筛选数据源

    Args:
        integration_type: 集成类型 — 'open_api' | 'scraper' | 'official_api' | 'self_hosted'

    Returns:
        该集成类型下的 SourceMeta 对象列表
    """
    return [meta for meta in _REGISTRY.values() if meta.integration_type == integration_type]


ALL_SOURCE_NAMES: frozenset[str] = frozenset(_REGISTRY.keys())
