"""Source package: youtube（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    YOUTUBE_PROVIDER_MANIFEST,
    YOUTUBE_PROVIDER_SPEC,
    _SPEC,
    VideoDetail,
    YouTubeClient,
    YouTubeClientProtocol,
    YouTubeSearchProvider,
    build_provider,
)
