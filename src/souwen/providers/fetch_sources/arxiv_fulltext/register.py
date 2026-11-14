"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.arxiv_fulltext import ArxivFulltextClient

from .adapter import ArxivFulltextFetchProvider
from .manifest import ARXIV_FULLTEXT_PROVIDER_MANIFEST
from .spec import ARXIV_FULLTEXT_FETCH_PROFILE


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, reviewed_proxy
    return ArxivFulltextFetchProvider(
        ArxivFulltextClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = ARXIV_FULLTEXT_PROVIDER_MANIFEST
SPEC = ARXIV_FULLTEXT_FETCH_PROFILE
PROVIDER_TYPE = ArxivFulltextFetchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
