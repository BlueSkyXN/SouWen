"""Source package: figshare（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    FIGSHARE_PROVIDER_MANIFEST,
    FIGSHARE_PROVIDER_SPEC,
    FigshareClient,
    FigshareClientProtocol,
    FigshareSearchProvider,
    build_provider,
)
