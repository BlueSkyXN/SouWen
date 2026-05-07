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
        tags=_T_HIGH_RISK,
        risk_reasons=frozenset({"account_ban", "quota_cost", "geo_sensitive"}),
    )
)

_reg(
    SourceAdapter(
        name="facebook",
        domain="social",
        integration="official_api",
        description="Facebook 页面/地点搜索（Graph API）",
        config_field="facebook_app_id",
        credential_fields=("facebook_app_id", "facebook_app_secret"),
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
