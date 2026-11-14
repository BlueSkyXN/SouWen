"""Source package: datacite（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    DATACITE_PROVIDER_MANIFEST,
    DATACITE_PROVIDER_SPEC,
    DataCiteClient,
    DataCiteClientProtocol,
    DataCiteSearchProvider,
    build_provider,
)
