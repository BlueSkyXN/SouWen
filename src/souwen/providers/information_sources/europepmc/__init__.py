"""Source package: europepmc（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    EUROPEPMC_PROVIDER_MANIFEST,
    EUROPEPMC_PROVIDER_SPEC,
    _SPEC,
    EuropePmcClient,
    EuropePmcClientProtocol,
    EuropePmcSearchProvider,
    build_provider,
)
