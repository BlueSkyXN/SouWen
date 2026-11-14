"""Source package: wayback（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    WAYBACK_PROVIDER_MANIFEST,
    WAYBACK_FETCH_PROVIDER_SPEC,
    _SPEC,
    WaybackClient,
    WaybackClientProtocol,
    WaybackFetchProvider,
    build_provider,
)
