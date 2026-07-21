"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_MAX_RESULTS,
)
from souwen.web.llm_search.registry import _SEARCH_SCHEMES
from souwen.web.llm_search.schemes.ark_annotations import (
    ARK_ANNOTATIONS_DEEPSEEK,
    ARK_ANNOTATIONS_DOUBAO,
    ARK_ANNOTATIONS_SCHEME,
)

# ═════════════════════════════════════════════════════════════
#  4b. web.api professional（AI/语义类授权 API）
# ═════════════════════════════════════════════════════════════

_SEARCH_SCHEMES.register_scheme(ARK_ANNOTATIONS_SCHEME)
for _ark_source, _ark_client_path, _ark_description in (
    (
        ARK_ANNOTATIONS_DEEPSEEK,
        "souwen.web.llm_search.schemes.ark_annotations:UniApiArkAnnotationsDeepSeekClient",
        "UniAPI Ark DeepSeek V3.2 网页搜索（结构化 citation，实验性）",
    ),
    (
        ARK_ANNOTATIONS_DOUBAO,
        "souwen.web.llm_search.schemes.ark_annotations:UniApiArkAnnotationsDoubaoClient",
        "UniAPI Ark Doubao Seed 2.0 Lite 网页搜索（结构化 citation，实验性）",
    ),
):
    _SEARCH_SCHEMES.register_source(_ark_source)
    _reg(
        _SEARCH_SCHEMES.project_source_adapter(
            _ark_source.source_id,
            description=_ark_description,
            client_loader=lazy(_ark_client_path),
            methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
            usage_note="实验性、默认关闭；仅在显式启用并配置 UniAPI Ark gateway 后调用。",
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

_reg(
    SourceAdapter(
        name="kimi_code",
        domain="web",
        integration="official_api",
        description="Kimi Code 搜索+网页获取",
        config_field="kimi_code_api_key",
        client_loader=lazy("souwen.web.kimi_code:KimiCodeClient"),
        extra_domains=frozenset({"fetch"}),
        methods={
            "search": MethodSpec("search", _P_MAX_RESULTS),
            "fetch": MethodSpec("fetch"),
        },
        category="web_professional",
    )
)
