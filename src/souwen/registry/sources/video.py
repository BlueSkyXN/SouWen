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
        optional_credential_effect="personalization",
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
