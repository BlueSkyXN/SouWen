"""历史导入路径转发：各源 client 已并入 information_sources/fetch_sources 的 source.py。"""

from __future__ import annotations

from souwen.providers.information_sources.datacite.source import DataCiteClient  # noqa: F401
from souwen.providers.information_sources.figshare.source import FigshareClient  # noqa: F401

__all__ = [
    "DataCiteClient",
    "FigshareClient",
]
