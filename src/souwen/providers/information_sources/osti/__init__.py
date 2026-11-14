"""Source package: osti（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    OSTI_PROVIDER_MANIFEST,
    OSTI_BRIDGE_SPEC,
    _BRIDGE_SPEC,
    OstiClient,
    OstiClientProtocol,
    OstiSearchProvider,
    build_provider,
)
