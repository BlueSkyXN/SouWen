"""Source package: uspto_odp（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    USPTO_ODP_PROVIDER_MANIFEST,
    USPTO_ODP_BRIDGE_SPEC,
    UsptoOdpClient,
    UsptoOdpClientProtocol,
    UsptoOdpSearchProvider,
    build_provider,
)
