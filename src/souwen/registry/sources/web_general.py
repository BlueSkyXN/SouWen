"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _T_HIGH_RISK,
    _P_MAX_RESULTS,
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
        category="web_general",
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
        default_for=frozenset({"web:search_news"}),
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        tags=_T_HIGH_RISK,
        category="web_general",
        risk_reasons=frozenset({"anti_scraping", "captcha", "ip_block"}),
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
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        tags=_T_HIGH_RISK,
        category="web_general",
        risk_reasons=frozenset({"anti_scraping", "captcha", "ip_block"}),
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
        category="web_general",
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
        category="web_general",
    )
)

# ═════════════════════════════════════════════════════════════
#  4. web.api（授权 API）
# ═════════════════════════════════════════════════════════════
# 按正式 catalog 划分：SERP 类（serpapi/brave_api/serper/scrapingdog/metaso）进 web_general，
# AI/语义类（tavily/exa/perplexity/firecrawl/linkup/xcrawl/zhipuai/aliyun_iqs）进 web_professional。

_reg(
    SourceAdapter(
        name="serpapi",
        domain="web",
        integration="official_api",
        description="SerpAPI 多引擎 SERP",
        config_field="serpapi_api_key",
        client_loader=lazy("souwen.web.serpapi:SerpApiClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        category="web_general",
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
        category="web_general",
    )
)

# ═════════════════════════════════════════════════════════════
#  5. web.self_hosted（自托管元搜索，3 个；对应 category="general"）
# ═════════════════════════════════════════════════════════════


def register_self_hosted() -> None:
    _reg(
        SourceAdapter(
            name="searxng",
            domain="web",
            integration="self_hosted",
            description="SearXNG 元搜索 (自建)",
            config_field="searxng_url",
            client_loader=lazy("souwen.web.searxng:SearXNGClient"),
            methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
            category="web_general",
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
            category="web_general",
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
            category="web_general",
        )
    )
