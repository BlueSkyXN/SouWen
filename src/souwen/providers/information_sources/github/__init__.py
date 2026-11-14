"""Source package: github（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    GITHUB_PROVIDER_MANIFEST,
    GITHUB_PROVIDER_SPEC,
    _SPEC,
    GitHubClient,
    GitHubClientProtocol,
    GitHubSearchProvider,
    build_provider,
)
