"""Source package: patentsview（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    PATENTSVIEW_PROVIDER_MANIFEST,
    PATENTSVIEW_REST_SPEC,
    _PATENTSVIEW_BRIDGE_SPEC,
    PatentsViewClient,
    PatentsViewClientProtocol,
    PatentsViewSearchProvider,
    build_provider,
    resolve_configuration,
)
