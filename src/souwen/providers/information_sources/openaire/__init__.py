"""Source package: openaire（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    OPENAIRE_PROVIDER_MANIFEST,
    OPENAIRE_PROVIDER_SPEC,
    _SPEC,
    OpenAireClient,
    OpenAireClientProtocol,
    OpenAireSearchProvider,
    build_provider,
)
