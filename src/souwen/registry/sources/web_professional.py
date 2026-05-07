"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_MAX_RESULTS,
)

# ═════════════════════════════════════════════════════════════
#  4b. web.api professional（AI/语义类授权 API）
# ═════════════════════════════════════════════════════════════

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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
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
        category="web_professional",
    )
)
