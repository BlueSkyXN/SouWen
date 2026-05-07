"""Shared helpers for built-in source declarations."""

from __future__ import annotations

from typing import Any

from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy
from souwen.registry.views import _reg

__all__ = (
    "MethodSpec",
    "SourceAdapter",
    "lazy",
    "_reg",
    "_T_HIGH_RISK",
    "_P_PER_PAGE",
    "_P_ROWS",
    "_P_RETMAX",
    "_P_SIZE",
    "_P_HITS",
    "_P_TOP_N",
    "_P_MAX_RESULTS",
    "_P_NUM_RESULTS",
    "_P_N_RESULTS",
    "_P_PAGE_SIZE",
    "_P_RANGE_END",
    "_patentsview_pre_call",
)

# 标签速记
_T_HIGH_RISK: frozenset[str] = frozenset({"high_risk"})

# 通用 param_map 速记
_P_PER_PAGE: dict[str, str] = {"limit": "per_page"}
_P_ROWS: dict[str, str] = {"limit": "rows"}
_P_RETMAX: dict[str, str] = {"limit": "retmax"}
_P_SIZE: dict[str, str] = {"limit": "size"}
_P_HITS: dict[str, str] = {"limit": "hits"}
_P_TOP_N: dict[str, str] = {"limit": "top_n"}
_P_MAX_RESULTS: dict[str, str] = {"limit": "max_results"}
_P_NUM_RESULTS: dict[str, str] = {"limit": "num_results"}
_P_N_RESULTS: dict[str, str] = {"limit": "n_results"}
_P_PAGE_SIZE: dict[str, str] = {"limit": "page_size"}
_P_RANGE_END: dict[str, str] = {"limit": "range_end", "query": "cql_query"}


def _patentsview_pre_call(params: dict[str, Any]) -> dict[str, Any]:
    """PatentsView 的 query 需要是 {"_contains": {"patent_title": q}} 结构。"""
    q = params.pop("query", None)
    if q is not None:
        params["query"] = {"_contains": {"patent_title": q}}
    return params
