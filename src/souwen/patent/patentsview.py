"""PatentsView API 客户端

USPTO 专利数据，免费无需 API Key。
官方文档: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.exceptions import NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

# PatentsView API 默认返回字段
_DEFAULT_PATENT_FIELDS = [
    "patent_id",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_num_claims",
    "patent_type",
    "application_number",
    "application_filing_date",
    "assignees",
    "inventors",
    "cpcs",
    "ipcs",
]


class PatentsViewClient:
    """PatentsView API 客户端

    免费访问 USPTO 专利数据，无需 API Key，零门槛。

    Attributes:
        BASE_URL: PatentsView API 基础地址
        RATE_LIMIT: 45 次/分钟 → 0.75 次/秒
    """

    BASE_URL = "https://search.patentsview.org/api/v1"
    RATE_LIMIT = 0.75  # 45 req/min

    def __init__(self) -> None:
        self._http = SouWenHttpClient(base_url=self.BASE_URL, source_name="patentsview")
        self._limiter = TokenBucketLimiter(rate=self.RATE_LIMIT, burst=3)

    async def __aenter__(self) -> PatentsViewClient:
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def close(self) -> None:
        """关闭 HTTP 连接"""
        await self._http.close()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: dict[str, Any],
        fields: list[str] | None = None,
        per_page: int = 10,
        page: int = 1,
        sort: list[dict[str, str]] | None = None,
    ) -> SearchResponse:
        """执行专利搜索

        Args:
            query: PatentsView JSON 查询过滤器，例如
                   ``{"_contains": {"patent_title": "neural network"}}``
            fields: 需返回的字段列表，默认使用 ``_DEFAULT_PATENT_FIELDS``
            per_page: 每页结果数
            page: 页码（从 1 开始）
            sort: 排序规则列表，例如 ``[{"patent_date": "desc"}]``

        Returns:
            SearchResponse 封装的搜索结果
        """
        payload: dict[str, Any] = {
            "q": query,
            "f": fields or _DEFAULT_PATENT_FIELDS,
            "o": {
                "per_page": per_page,
                "page": page,
            },
        }
        if sort:
            payload["s"] = sort

        await self._limiter.acquire()
        resp = await self._http.post("/patent/", json=payload)
        data = self._parse_json(resp)

        patents = [self._to_patent_result(p) for p in data.get("patents", [])]
        return SearchResponse(
            query=str(query),
            source=SourceType.PATENTSVIEW,
            total_results=data.get("total_patent_count"),
            results=patents,
            page=page,
            per_page=per_page,
        )

    async def get_patent(self, patent_id: str) -> PatentResult:
        """根据专利号获取详情

        Args:
            patent_id: USPTO 专利号，例如 ``"11234567"``

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        query = {"_equals": {"patent_id": patent_id}}
        payload = {
            "q": query,
            "f": _DEFAULT_PATENT_FIELDS,
            "o": {"per_page": 1, "page": 1},
        }

        await self._limiter.acquire()
        resp = await self._http.post("/patent/", json=payload)
        data = self._parse_json(resp)

        patents = data.get("patents", [])
        if not patents:
            raise NotFoundError(f"专利 {patent_id} 未找到")
        return self._to_patent_result(patents[0])

    async def search_by_assignee(
        self,
        org_name: str,
        per_page: int = 10,
    ) -> SearchResponse:
        """按受让人/申请人组织名检索

        Args:
            org_name: 组织名称
            per_page: 每页结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        query = {"_contains": {"assignees.assignee_organization": org_name}}
        return await self.search(query, per_page=per_page)

    async def search_by_inventor(
        self,
        inventor_name: str,
        per_page: int = 10,
    ) -> SearchResponse:
        """按发明人姓名检索

        Args:
            inventor_name: 发明人姓名
            per_page: 每页结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        query = {
            "_or": [
                {"_contains": {"inventors.inventor_first_name": inventor_name}},
                {"_contains": {"inventors.inventor_last_name": inventor_name}},
            ]
        }
        return await self.search(query, per_page=per_page)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"PatentsView 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 PatentsView 原始数据转换为 PatentResult 模型"""
        # 受让人列表
        applicants: list[Applicant] = []
        for a in raw.get("assignees", []) or []:
            name = (
                a.get("assignee_organization")
                or f"{a.get('assignee_first_name', '')} {a.get('assignee_last_name', '')}".strip()
            )
            if name:
                applicants.append(Applicant(name=name, country=a.get("assignee_country")))

        # 发明人列表
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            full = (
                f"{inv.get('inventor_first_name', '')} {inv.get('inventor_last_name', '')}".strip()
            )
            if full:
                inventors.append(full)

        # CPC / IPC 分类号
        cpc_codes = [
            c.get("cpc_group_id", "") for c in (raw.get("cpcs", []) or []) if c.get("cpc_group_id")
        ]
        ipc_codes = [
            i.get("ipc_group", "") for i in (raw.get("ipcs", []) or []) if i.get("ipc_group")
        ]

        patent_id = raw.get("patent_id", "")
        return PatentResult(
            source=SourceType.PATENTSVIEW,
            title=raw.get("patent_title", ""),
            patent_id=patent_id,
            application_number=raw.get("application_number"),
            publication_date=_safe_date(raw.get("patent_date")),
            filing_date=_safe_date(raw.get("application_filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("patent_abstract"),
            cpc_codes=cpc_codes,
            ipc_codes=ipc_codes,
            source_url=f"https://search.patentsview.org/patent/{patent_id}",
            raw=raw,
        )


def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串 (YYYY-MM-DD)"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
