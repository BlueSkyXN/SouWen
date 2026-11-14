"""Source package: doaj（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    DOAJ_PROVIDER_MANIFEST,
    DOAJ_PROVIDER_SPEC,
    _SPEC,
    DoajClient,
    DoajClientProtocol,
    DoajSearchProvider,
    build_provider,
)
