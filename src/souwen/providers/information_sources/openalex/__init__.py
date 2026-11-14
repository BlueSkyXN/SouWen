"""Source package: openalex（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    OPENALEX_PROVIDER_MANIFEST,
    OPENALEX_REST_SPEC,
    _OPENALEX_BRIDGE_SPEC,
    OpenAlexClient,
    OpenAlexClientProtocol,
    OpenAlexSearchProvider,
    build_provider,
    resolve_configuration,
)
