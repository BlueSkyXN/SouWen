"""Source package: yahoo（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    YahooClient,
    YahooSearchProvider,
    MANIFEST,
    SPEC,
    PROVIDER_TYPE,
    build_provider,
)

YAHOO_PROVIDER_MANIFEST = MANIFEST
YAHOO_PROVIDER_SPEC = SPEC
