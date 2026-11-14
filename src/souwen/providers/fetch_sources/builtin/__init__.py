"""Source package: builtin（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    BUILTIN_FETCH_MANIFEST,
    BuiltinFetchProvider,
    BuiltinFetchClientProtocol,
    MANIFEST,
    PROVIDER_TYPE,
    build_provider,
)
