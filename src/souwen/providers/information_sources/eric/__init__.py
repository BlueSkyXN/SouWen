"""Source package: eric（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    ERIC_PROVIDER_MANIFEST,
    ERIC_REST_SPEC,
    EricClient,
    EricClientProtocol,
    EricSearchProvider,
    build_provider,
    resolve_configuration,
)
