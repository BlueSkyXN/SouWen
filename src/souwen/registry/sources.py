"""registry/sources.py — 声明式数据源注册

**这是单一事实源**。新增一个数据源 = 在这个文件里加一个 `_reg(SourceAdapter(...))`。

组织顺序：
  1. paper（19 源）
  2. patent（8 源）
  3. web.engines（爬虫类 SERP，13 个）
  4. web.api（授权 API，13 个）
  5. web.self_hosted（自托管元搜索，3 个）
  6. social（5 源）
  7. video（2 源）
  8. knowledge（1 源 Wikipedia；DeepWiki 归 fetch）
  9. developer（2 源）
 10. cn_tech（9 源）
 11. office（1 源）
 12. archive（1 源：Wayback，extra_domains={"fetch"}）
 13. fetch providers（16 个横切 + 上面 5 个跨域源）

注意：
  - `client_loader` 使用 `lazy("path:Class")` 字符串懒加载，registry 模块导入时
    **不会**把 80+ 个 Client 全部 import 进来。
  - `param_map` 把统一入参（limit/query）翻译为源原生参数名（per_page/rows/retmax/size/...）。
  - `default_for` 声明 (domain, capability) 下的默认源。
  - `tags={"v0_category:general"}` / `{"v0_category:professional"}` 用于 ALL_SOURCES 分类映射
    （让 `as_all_sources_dict()` 能正确派生 general / professional 划分）。

本文件的变更会被 `tests/registry/test_consistency.py` 验证：
  - 所有 client_loader 的目标类真实存在
  - 所有 method_name 在客户端类上可解析
  - 所有 param_map 的原生参数名都是方法签名的真实参数
"""

from __future__ import annotations

from typing import Any

from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy
from souwen.registry.views import _reg  # 模块内使用的注册函数

# ALL_SOURCES 分类标签速记
_T_GENERAL: frozenset[str] = frozenset({"v0_category:general"})
_T_PROFESSIONAL: frozenset[str] = frozenset({"v0_category:professional"})
_T_HIGH_RISK_GENERAL: frozenset[str] = frozenset({"v0_category:general", "high_risk"})
_T_HIGH_RISK_SOCIAL: frozenset[str] = frozenset({"high_risk"})

# 通用 param_map 速记
_P_PER_PAGE: dict[str, str] = {"limit": "per_page"}
_P_ROWS: dict[str, str] = {"limit": "rows"}
_P_RETMAX: dict[str, str] = {"limit": "retmax"}
_P_SIZE: dict[str, str] = {"limit": "size"}
_P_HITS: dict[str, str] = {"limit": "hits"}
_P_TOP_N: dict[str, str] = {"limit": "top_n"}
_P_MAX_RESULTS: dict[str, str] = {"limit": "max_results"}
_P_NUM_RESULTS: dict[str, str] = {"limit": "num_results"}
_P_N_RESULTS: dict[str, str] = {"limit": "n_results"}
_P_PAGE_SIZE: dict[str, str] = {"limit": "page_size"}
_P_RANGE_END: dict[str, str] = {"limit": "range_end", "query": "cql_query"}


# ═════════════════════════════════════════════════════════════
#  1. paper（19 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="openalex",
        domain="paper",
        integration="open_api",
        description="OpenAlex 开放学术数据",
        config_field="openalex_email",  # 可选 email（提升速率限制）
        needs_config=False,  # 零配置可用
        client_loader=lazy("souwen.paper.openalex:OpenAlexClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="semantic_scholar",
        domain="paper",
        integration="official_api",
        description="Semantic Scholar API",
        config_field="semantic_scholar_api_key",
        needs_config=False,  # 免 Key 可试用
        client_loader=lazy("souwen.paper.semantic_scholar:SemanticScholarClient"),
        methods={"search": MethodSpec("search")},  # limit → limit 同名
    )
)

_reg(
    SourceAdapter(
        name="crossref",
        domain="paper",
        integration="open_api",
        description="CrossRef 跨库检索",
        config_field=None,
        client_loader=lazy("souwen.paper.crossref:CrossrefClient"),
        methods={"search": MethodSpec("search", _P_ROWS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="arxiv",
        domain="paper",
        integration="open_api",
        description="arXiv 预印本",
        config_field=None,
        client_loader=lazy("souwen.paper.arxiv:ArxivClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="dblp",
        domain="paper",
        integration="open_api",
        description="DBLP 计算机科学文献",
        config_field=None,
        client_loader=lazy("souwen.paper.dblp:DblpClient"),
        methods={"search": MethodSpec("search", _P_HITS)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="core",
        domain="paper",
        integration="official_api",
        description="CORE 开放获取聚合",
        config_field="core_api_key",
        client_loader=lazy("souwen.paper.core:CoreClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="pubmed",
        domain="paper",
        integration="open_api",
        description="PubMed 生物医学",
        config_field=None,
        client_loader=lazy("souwen.paper.pubmed:PubMedClient"),
        methods={"search": MethodSpec("search", _P_RETMAX)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="biorxiv",
        domain="paper",
        integration="open_api",
        description="bioRxiv/medRxiv 生物医学预印本",
        config_field=None,
        client_loader=lazy("souwen.paper.biorxiv:BioRxivClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
        default_for=frozenset({"paper:search"}),
    )
)

_reg(
    SourceAdapter(
        name="zotero",
        domain="paper",
        integration="official_api",
        description="Zotero 个人文献库搜索 (需 API Key + Library ID)",
        config_field="zotero_api_key",
        client_loader=lazy("souwen.paper.zotero:ZoteroClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="huggingface",
        domain="paper",
        integration="open_api",
        description="HuggingFace Papers 社区精选（语义搜索 + 热度排行，无需 Key）",
        config_field=None,
        client_loader=lazy("souwen.paper.huggingface:HuggingFaceClient"),
        methods={"search": MethodSpec("search", _P_TOP_N)},
    )
)

_reg(
    SourceAdapter(
        name="europepmc",
        domain="paper",
        integration="open_api",
        description="Europe PMC 欧洲生物医学文献",
        config_field=None,
        client_loader=lazy("souwen.paper.europepmc:EuropePmcClient"),
        methods={"search": MethodSpec("search", _P_PAGE_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="pmc",
        domain="paper",
        integration="open_api",
        description="PubMed Central 生物医学全文",
        config_field=None,
        client_loader=lazy("souwen.paper.pmc:PmcClient"),
        methods={"search": MethodSpec("search", _P_RETMAX)},
    )
)

_reg(
    SourceAdapter(
        name="doaj",
        domain="paper",
        integration="official_api",
        description="DOAJ 开放获取期刊目录（可选 Key）",
        config_field="doaj_api_key",
        needs_config=False,  # 可选 Key
        client_loader=lazy("souwen.paper.doaj:DoajClient"),
        methods={"search": MethodSpec("search", _P_PAGE_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="zenodo",
        domain="paper",
        integration="official_api",
        description="Zenodo CERN 开放科学仓库（可选 Token）",
        config_field="zenodo_access_token",
        needs_config=False,  # 可选 Token
        client_loader=lazy("souwen.paper.zenodo:ZenodoClient"),
        methods={"search": MethodSpec("search", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="hal",
        domain="paper",
        integration="open_api",
        description="HAL 法国开放档案（Solr API）",
        config_field=None,
        client_loader=lazy("souwen.paper.hal:HalClient"),
        methods={"search": MethodSpec("search", _P_ROWS)},
    )
)

_reg(
    SourceAdapter(
        name="openaire",
        domain="paper",
        integration="official_api",
        description="OpenAIRE 欧盟研究基础设施（可选 Key）",
        config_field="openaire_api_key",
        needs_config=False,  # 可选 Key
        client_loader=lazy("souwen.paper.openaire:OpenAireClient"),
        methods={"search": MethodSpec("search", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="iacr",
        domain="paper",
        integration="scraper",
        description="IACR ePrint 密码学预印本（实验性 HTML 爬虫）",
        config_field=None,
        client_loader=lazy("souwen.paper.iacr:IacrClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="ieee_xplore",
        domain="paper",
        integration="official_api",
        description="IEEE Xplore 电气电子工程文献",
        config_field="ieee_api_key",
        client_loader=lazy("souwen.paper.ieee_xplore:IeeeXploreClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="unpaywall",
        domain="paper",
        integration="official_api",
        description="Unpaywall OA 查找",
        config_field="unpaywall_email",
        needs_config=False,  # email 可选
        client_loader=lazy("souwen.paper.unpaywall:UnpaywallClient"),
        # unpaywall 没有 search 方法，只有 find_oa(doi)；用命名空间声明（D8）
        methods={"unpaywall:find_oa": MethodSpec("find_oa")},
        # 不参与 search 调度，ALL_SOURCES["paper"] 也不收录
        tags=frozenset({"v0_all_sources:exclude"}),
    )
)


# ═════════════════════════════════════════════════════════════
#  2. patent（8 源）
# ═════════════════════════════════════════════════════════════


def _patentsview_pre_call(params: dict[str, Any]) -> dict[str, Any]:
    """PatentsView 的 query 需要是 {"_contains": {"patent_title": q}} 结构。"""
    q = params.pop("query", None)
    if q is not None:
        params["query"] = {"_contains": {"patent_title": q}}
    return params


_reg(
    SourceAdapter(
        name="patentsview",
        domain="patent",
        integration="open_api",
        description="PatentsView 美国专利 (待修复)",
        config_field=None,
        client_loader=lazy("souwen.patent.patentsview:PatentsViewClient"),
        methods={
            "search": MethodSpec(
                "search",
                _P_PER_PAGE,
                pre_call=_patentsview_pre_call,
            ),
        },
        # "待修复"状态，ALL_SOURCES["patent"] 也不收录
        tags=frozenset({"v0_all_sources:exclude"}),
    )
)

_reg(
    SourceAdapter(
        name="pqai",
        domain="patent",
        integration="open_api",
        description="PQAI 专利语义搜索 (待修复)",
        config_field=None,
        client_loader=lazy("souwen.patent.pqai:PqaiClient"),
        methods={"search": MethodSpec("search", _P_N_RESULTS)},
        tags=frozenset({"v0_all_sources:exclude"}),
    )
)

_reg(
    SourceAdapter(
        name="epo_ops",
        domain="patent",
        integration="official_api",
        description="EPO OPS 欧洲专利局",
        config_field="epo_consumer_key",
        client_loader=lazy("souwen.patent.epo_ops:EpoOpsClient"),
        # epo_ops 的方法是 search(cql_query, range_end)
        methods={"search": MethodSpec("search", _P_RANGE_END)},
    )
)

_reg(
    SourceAdapter(
        name="uspto_odp",
        domain="patent",
        integration="official_api",
        description="USPTO ODP 美国专利局",
        config_field="uspto_api_key",
        client_loader=lazy("souwen.patent.uspto_odp:UsptoOdpClient"),
        # 方法名是 search_applications，统一到 'search' capability
        methods={"search": MethodSpec("search_applications", _P_PER_PAGE)},
    )
)

_reg(
    SourceAdapter(
        name="the_lens",
        domain="patent",
        integration="official_api",
        description="The Lens 专利+学术",
        config_field="lens_api_token",
        client_loader=lazy("souwen.patent.the_lens:TheLensClient"),
        methods={"search": MethodSpec("search_patents", _P_SIZE)},
    )
)

_reg(
    SourceAdapter(
        name="cnipa",
        domain="patent",
        integration="official_api",
        description="CNIPA 中国国知局",
        config_field="cnipa_client_id",
        client_loader=lazy("souwen.patent.cnipa:CnipaClient"),
        methods={"search": MethodSpec("search", _P_PER_PAGE)},
    )
)

_reg(
    SourceAdapter(
        name="patsnap",
        domain="patent",
        integration="official_api",
        description="PatSnap 智慧芽",
        config_field="patsnap_api_key",
        client_loader=lazy("souwen.patent.patsnap:PatSnapClient"),
        methods={"search": MethodSpec("search")},  # limit → limit
    )
)

_reg(
    SourceAdapter(
        name="google_patents",
        domain="patent",
        integration="scraper",
        description="Google Patents 爬虫",
        config_field=None,
        # v1 统一：由 GooglePatentsScraper 承担（P1 阶段会合并到 patent/google_patents.py）
        client_loader=lazy("souwen.scraper.google_patents_scraper:GooglePatentsScraper"),
        methods={"search": MethodSpec("search", _P_NUM_RESULTS)},
        default_for=frozenset({"patent:search"}),
    )
)


# ═════════════════════════════════════════════════════════════
#  3. web.engines（爬虫类 SERP，13 个；对应 category="general"）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="duckduckgo",
        domain="web",
        integration="scraper",
        description="DuckDuckGo 网页搜索",
        config_field=None,
        client_loader=lazy("souwen.web.duckduckgo:DuckDuckGoClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"web:search"}),
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="duckduckgo_news",
        domain="web",
        integration="scraper",
        description="DuckDuckGo 新闻搜索",
        config_field=None,
        client_loader=lazy("souwen.web.ddg_news:DuckDuckGoNewsClient"),
        methods={"search_news": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="duckduckgo_images",
        domain="web",
        integration="scraper",
        description="DuckDuckGo 图片搜索",
        config_field=None,
        client_loader=lazy("souwen.web.ddg_images:DuckDuckGoImagesClient"),
        methods={"search_images": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="duckduckgo_videos",
        domain="web",
        integration="scraper",
        description="DuckDuckGo 视频搜索",
        config_field=None,
        client_loader=lazy("souwen.web.ddg_videos:DuckDuckGoVideosClient"),
        methods={"search_videos": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="yahoo",
        domain="web",
        integration="scraper",
        description="Yahoo 搜索",
        config_field=None,
        client_loader=lazy("souwen.web.yahoo:YahooClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="brave",
        domain="web",
        integration="scraper",
        description="Brave 搜索",
        config_field=None,
        client_loader=lazy("souwen.web.brave:BraveClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="google",
        domain="web",
        integration="scraper",
        description="Google 搜索（高风险，易被限流/封禁）",
        config_field=None,
        client_loader=lazy("souwen.web.google:GoogleClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_enabled=False,  # D10：高风险
        tags=_T_HIGH_RISK_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="bing",
        domain="web",
        integration="scraper",
        description="Bing 搜索",
        config_field=None,
        client_loader=lazy("souwen.web.bing:BingClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"web:search"}),
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="bing_cn",
        domain="web",
        integration="scraper",
        description="必应中文搜索 (cn.bing.com)",
        config_field=None,
        client_loader=lazy("souwen.web.bing_cn:BingCnClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="startpage",
        domain="web",
        integration="scraper",
        description="Startpage 隐私搜索",
        config_field=None,
        client_loader=lazy("souwen.web.startpage:StartpageClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="baidu",
        domain="web",
        integration="scraper",
        description="百度搜索（高风险，易被反爬）",
        config_field=None,
        client_loader=lazy("souwen.web.baidu:BaiduClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_enabled=False,
        tags=_T_HIGH_RISK_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="mojeek",
        domain="web",
        integration="scraper",
        description="Mojeek 独立搜索",
        config_field=None,
        client_loader=lazy("souwen.web.mojeek:MojeekClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="yandex",
        domain="web",
        integration="scraper",
        description="Yandex 搜索",
        config_field=None,
        client_loader=lazy("souwen.web.yandex:YandexClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)


# ═════════════════════════════════════════════════════════════
#  4. web.api（授权 API）
# ═════════════════════════════════════════════════════════════
# 按 ALL_SOURCES 的划分：SERP 类（serpapi/brave_api/serper/scrapingdog/metaso）进 general，
# AI/语义类（tavily/exa/perplexity/firecrawl/linkup/xcrawl/zhipuai/aliyun_iqs）进 professional。

_reg(
    SourceAdapter(
        name="serpapi",
        domain="web",
        integration="official_api",
        description="SerpAPI 多引擎 SERP",
        config_field="serpapi_api_key",
        client_loader=lazy("souwen.web.serpapi:SerpApiClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="brave_api",
        domain="web",
        integration="official_api",
        description="Brave Search API",
        config_field="brave_api_key",
        client_loader=lazy("souwen.web.brave_api:BraveApiClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="serper",
        domain="web",
        integration="official_api",
        description="Serper Google SERP",
        config_field="serper_api_key",
        client_loader=lazy("souwen.web.serper:SerperClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="scrapingdog",
        domain="web",
        integration="official_api",
        description="ScrapingDog SERP",
        config_field="scrapingdog_api_key",
        client_loader=lazy("souwen.web.scrapingdog:ScrapingDogClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="metaso",
        domain="web",
        integration="official_api",
        description="Metaso 秘塔搜索 (文档/网页/学术)",
        config_field="metaso_api_key",
        client_loader=lazy("souwen.web.metaso:MetasoClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="tavily",
        domain="web",
        integration="official_api",
        description="Tavily AI 搜索",
        config_field="tavily_api_key",
        client_loader=lazy("souwen.web.tavily:TavilyClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "fetch": MethodSpec("extract"),
        },
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="exa",
        domain="web",
        integration="official_api",
        description="Exa 语义搜索",
        config_field="exa_api_key",
        client_loader=lazy("souwen.web.exa:ExaClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "fetch": MethodSpec("contents"),
            "exa:find_similar": MethodSpec("find_similar", _P_MAX_RESULTS),  # D8 命名空间
        },
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="perplexity",
        domain="web",
        integration="official_api",
        description="Perplexity Sonar AI",
        config_field="perplexity_api_key",
        client_loader=lazy("souwen.web.perplexity:PerplexityClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="firecrawl",
        domain="web",
        integration="official_api",
        description="Firecrawl 搜索+爬取",
        config_field="firecrawl_api_key",
        client_loader=lazy("souwen.web.firecrawl:FirecrawlClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "fetch": MethodSpec("scrape"),
        },
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="linkup",
        domain="web",
        integration="official_api",
        description="Linkup 实时搜索",
        config_field="linkup_api_key",
        client_loader=lazy("souwen.web.linkup:LinkupClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="xcrawl",
        domain="web",
        integration="official_api",
        description="XCrawl 搜索+抓取",
        config_field="xcrawl_api_key",
        client_loader=lazy("souwen.web.xcrawl:XCrawlClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "fetch": MethodSpec("scrape"),
        },
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="zhipuai",
        domain="web",
        integration="official_api",
        description="智谱 AI Web Search Pro (含 AI 摘要，支持中文)",
        config_field="zhipuai_api_key",
        client_loader=lazy("souwen.web.zhipuai_search:ZhipuAISearchClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_PROFESSIONAL,
    )
)

_reg(
    SourceAdapter(
        name="aliyun_iqs",
        domain="web",
        integration="official_api",
        description="阿里云 IQS 通义晓搜 (含 AI 摘要，支持中文)",
        config_field="aliyun_iqs_api_key",
        client_loader=lazy("souwen.web.aliyun_iqs:AliyunIQSClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_PROFESSIONAL,
    )
)


# ═════════════════════════════════════════════════════════════
#  5. web.self_hosted（自托管元搜索，3 个；对应 category="general"）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="searxng",
        domain="web",
        integration="self_hosted",
        description="SearXNG 元搜索 (自建)",
        config_field="searxng_url",
        client_loader=lazy("souwen.web.searxng:SearXNGClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="whoogle",
        domain="web",
        integration="self_hosted",
        description="Whoogle Google 代理 (自建)",
        config_field="whoogle_url",
        client_loader=lazy("souwen.web.whoogle:WhoogleClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)

_reg(
    SourceAdapter(
        name="websurfx",
        domain="web",
        integration="self_hosted",
        description="Websurfx 聚合搜索 (自建)",
        config_field="websurfx_url",
        client_loader=lazy("souwen.web.websurfx:WebsurfxClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        tags=_T_GENERAL,
    )
)


# ═════════════════════════════════════════════════════════════
#  6. social（5 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="reddit",
        domain="social",
        integration="open_api",
        description="Reddit 帖子搜索",
        config_field=None,
        client_loader=lazy("souwen.web.reddit:RedditClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="twitter",
        domain="social",
        integration="official_api",
        description="Twitter/X 推文搜索（API v2，高风险：限流严格）",
        config_field="twitter_bearer_token",
        client_loader=lazy("souwen.web.twitter:TwitterClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_enabled=False,
        tags=_T_HIGH_RISK_SOCIAL,
    )
)

_reg(
    SourceAdapter(
        name="facebook",
        domain="social",
        integration="official_api",
        description="Facebook 页面/地点搜索（Graph API）",
        config_field="facebook_app_id",
        client_loader=lazy("souwen.web.facebook:FacebookClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="weibo",
        domain="social",
        integration="scraper",
        description="微博搜索",
        config_field=None,
        client_loader=lazy("souwen.web.weibo:WeiboClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="zhihu",
        domain="social",
        integration="scraper",
        description="知乎问答搜索",
        config_field=None,
        client_loader=lazy("souwen.web.zhihu:ZhihuClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)


# ═════════════════════════════════════════════════════════════
#  7. video（2 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="youtube",
        domain="video",
        integration="official_api",
        description="YouTube 视频搜索",
        config_field="youtube_api_key",
        client_loader=lazy("souwen.web.youtube:YouTubeClient"),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "get_trending": MethodSpec("get_trending", _P_MAX_RESULTS),
            "get_detail": MethodSpec("get_video_details"),
            "get_transcript": MethodSpec("get_transcript"),
        },
        default_for=frozenset({"video:search"}),
    )
)

_reg(
    SourceAdapter(
        name="bilibili",
        domain="video",
        integration="scraper",
        description="Bilibili 搜索（视频/用户/专栏文章）+ 视频详情抓取",
        config_field="bilibili_sessdata",
        needs_config=False,  # sessdata 可选
        client_loader=lazy("souwen.web.bilibili:BilibiliClient"),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "search_articles": MethodSpec("search_articles"),
            "search_users": MethodSpec("search_users"),
            "get_detail": MethodSpec("get_video_details"),
        },
        default_for=frozenset({"video:search"}),
    )
)


# ═════════════════════════════════════════════════════════════
#  8. knowledge（1 源：Wikipedia；DeepWiki 归 fetch）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="wikipedia",
        domain="knowledge",
        integration="open_api",
        description="Wikipedia 百科搜索",
        config_field=None,
        client_loader=lazy("souwen.web.wikipedia:WikipediaClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"knowledge:search"}),
    )
)


# ═════════════════════════════════════════════════════════════
#  9. developer（2 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="github",
        domain="developer",
        integration="open_api",
        description="GitHub 仓库搜索 (可选 Token)",
        config_field="github_token",
        needs_config=False,  # Token 可选
        client_loader=lazy("souwen.web.github:GitHubClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"developer:search"}),
    )
)

_reg(
    SourceAdapter(
        name="stackoverflow",
        domain="developer",
        integration="open_api",
        description="StackOverflow 问答搜索",
        config_field="stackoverflow_api_key",
        needs_config=False,  # Key 可选
        client_loader=lazy("souwen.web.stackoverflow:StackOverflowClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        default_for=frozenset({"developer:search"}),
    )
)


# ═════════════════════════════════════════════════════════════
# 10. cn_tech（9 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="csdn",
        domain="cn_tech",
        integration="scraper",
        description="CSDN 技术博客搜索",
        config_field=None,
        client_loader=lazy("souwen.web.csdn:CSDNClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="juejin",
        domain="cn_tech",
        integration="scraper",
        description="稀土掘金技术文章搜索",
        config_field=None,
        client_loader=lazy("souwen.web.juejin:JuejinClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="linuxdo",
        domain="cn_tech",
        integration="open_api",
        description="LinuxDo 论坛搜索（Discourse）",
        config_field=None,
        client_loader=lazy("souwen.web.linuxdo:LinuxDoClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="nodeseek",
        domain="cn_tech",
        integration="scraper",
        description="NodeSeek 社区搜索（DDG site:nodeseek.com）",
        config_field=None,
        client_loader=lazy("souwen.web.nodeseek:NodeSeekClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="hostloc",
        domain="cn_tech",
        integration="scraper",
        description="HostLoc 论坛搜索（DDG site:hostloc.com）",
        config_field=None,
        client_loader=lazy("souwen.web.hostloc:HostLocClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="v2ex",
        domain="cn_tech",
        integration="scraper",
        description="V2EX 社区搜索（DDG site:v2ex.com）",
        config_field=None,
        client_loader=lazy("souwen.web.v2ex:V2EXClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="coolapk",
        domain="cn_tech",
        integration="scraper",
        description="Coolapk 社区搜索（DDG site:coolapk.com）",
        config_field=None,
        client_loader=lazy("souwen.web.coolapk:CoolapkClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="xiaohongshu",
        domain="cn_tech",
        integration="scraper",
        description="小红书搜索（DDG site:xiaohongshu.com）",
        config_field=None,
        client_loader=lazy("souwen.web.xiaohongshu:XiaohongshuClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="community_cn",
        domain="cn_tech",
        integration="scraper",
        description="【已弃用兼容入口】中文社区聚合搜索（请改用 linuxdo/nodeseek/hostloc/v2ex/coolapk/xiaohongshu）",
        config_field=None,
        client_loader=lazy("souwen.web.community_cn:CommunityCnClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)


# ═════════════════════════════════════════════════════════════
# 11. office（1 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="feishu_drive",
        domain="office",
        integration="official_api",
        description="飞书云文档搜索 (需 App ID + App Secret)",
        config_field="feishu_app_id",
        client_loader=lazy("souwen.web.feishu_drive:FeishuDriveClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)


# ═════════════════════════════════════════════════════════════
# 12. archive（Wayback，主 domain=archive，extra_domains={"fetch"}）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="wayback",
        domain="archive",
        integration="open_api",
        description="Internet Archive Wayback (免费)",
        config_field=None,
        client_loader=lazy("souwen.web.wayback:WaybackClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "archive_lookup": MethodSpec("query_snapshots"),
            "archive_save": MethodSpec("save_page"),
            "fetch": MethodSpec("fetch"),
        },
        default_for=frozenset({"archive:archive_lookup"}),
    )
)


# ═════════════════════════════════════════════════════════════
# 13. fetch providers（16 个横切，仅 fetch capability）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="builtin",
        domain="fetch",
        integration="scraper",
        description="内置抓取 (httpx/curl_cffi + trafilatura, 零配置)",
        config_field=None,
        client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        default_for=frozenset({"fetch:fetch"}),
    )
)

_reg(
    SourceAdapter(
        name="jina_reader",
        domain="fetch",
        integration="open_api",
        description="Jina Reader 内容抓取 (免费, 可选 Key)",
        config_field="jina_api_key",
        needs_config=False,  # Key 可选
        client_loader=lazy("souwen.web.jina_reader:JinaReaderClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="arxiv_fulltext",
        domain="fetch",
        integration="open_api",
        description="arXiv 论文全文抓取（按 arxiv.org 论文 URL 提取正文）",
        config_field=None,
        client_loader=lazy("souwen.paper.arxiv_fulltext:ArxivFulltextClient"),
        methods={"fetch": MethodSpec("get_fulltext")},
    )
)

_reg(
    SourceAdapter(
        name="crawl4ai",
        domain="fetch",
        integration="scraper",
        description="Crawl4AI 无头浏览器抓取 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.crawl4ai_fetcher:Crawl4AIFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="scrapfly",
        domain="fetch",
        integration="official_api",
        description="Scrapfly JS 渲染 + AI 抽取",
        config_field="scrapfly_api_key",
        client_loader=lazy("souwen.web.scrapfly:ScrapflyClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="diffbot",
        domain="fetch",
        integration="official_api",
        description="Diffbot 结构化文章抽取",
        config_field="diffbot_api_token",
        client_loader=lazy("souwen.web.diffbot:DiffbotClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="scrapingbee",
        domain="fetch",
        integration="official_api",
        description="ScrapingBee 代理 + JS 渲染",
        config_field="scrapingbee_api_key",
        client_loader=lazy("souwen.web.scrapingbee:ScrapingBeeClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="zenrows",
        domain="fetch",
        integration="official_api",
        description="ZenRows 代理 + JS 渲染 + 反爬",
        config_field="zenrows_api_key",
        client_loader=lazy("souwen.web.zenrows:ZenRowsClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="scraperapi",
        domain="fetch",
        integration="official_api",
        description="ScraperAPI 代理池 + JS 渲染",
        config_field="scraperapi_api_key",
        client_loader=lazy("souwen.web.scraperapi:ScraperAPIClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="apify",
        domain="fetch",
        integration="official_api",
        description="Apify Actor 爬虫平台",
        config_field="apify_api_token",
        client_loader=lazy("souwen.web.apify:ApifyClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="cloudflare",
        domain="fetch",
        integration="official_api",
        description="Cloudflare Browser Rendering",
        config_field="cloudflare_api_token",
        client_loader=lazy("souwen.web.cloudflare_browser:CloudflareBrowserClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="newspaper",
        domain="fetch",
        integration="scraper",
        description="newspaper4k 文章抽取 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.newspaper_fetcher:NewspaperFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="readability",
        domain="fetch",
        integration="scraper",
        description="Mozilla Readability 算法 (本地)",
        config_field=None,
        client_loader=lazy("souwen.web.readability_fetcher:ReadabilityFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="mcp",
        domain="fetch",
        integration="open_api",
        description="MCP 协议内容抓取 (外部工具)",
        config_field=None,
        client_loader=lazy("souwen.web.mcp_fetch:MCPFetchClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)

_reg(
    SourceAdapter(
        name="site_crawler",
        domain="fetch",
        integration="scraper",
        description="BFS 站点爬虫 (批量多页面)",
        config_field=None,
        client_loader=lazy("souwen.web.site_crawler:SiteCrawlerClient"),
        methods={"fetch": MethodSpec("fetch_batch")},  # 站点爬虫本身就是批量
    )
)

_reg(
    SourceAdapter(
        name="deepwiki",
        domain="fetch",
        integration="open_api",
        description="DeepWiki 开源项目文档抓取 (免费)",
        config_field=None,
        client_loader=lazy("souwen.web.deepwiki:DeepWikiClient"),
        methods={"fetch": MethodSpec("fetch")},
    )
)
