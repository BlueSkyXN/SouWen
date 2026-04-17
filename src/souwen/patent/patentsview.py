"""PatentsView API 客户端

USPTO 专利数据，免费无需 API Key。
官方文档: https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference

文件用途：
    PatentsView API 客户端，提供免费的 USPTO 专利数据访问。
    支持灵活的 JSON 查询过滤语法（Elasticsearch-like DSL）。
    包含按受让人、发明人等多维度搜索的便利方法。

函数/类清单：
    PatentsViewClient（类）
        - 功能：PatentsView API 客户端，管理 HTTP 连接和速率限制
        - 关键属性：BASE_URL (str) API 基础地址，RATE_LIMIT (float) 限流速率
        - 关键变量：_http (SouWenHttpClient) HTTP 客户端，_limiter 速率限制器

    search(query: dict, fields: list | None = None, per_page: int = 10, page: int = 1, sort: list | None = None) -> SearchResponse
        - 功能：执行灵活的专利搜索
        - 输入：query PatentsView JSON 查询过滤器，fields 返回字段列表，per_page 分页大小，page 页码，sort 排序规则
        - 输出：SearchResponse 包含总数、结果列表、分页信息

    get_patent(patent_id: str) -> PatentResult
        - 功能：根据 USPTO 专利号获取详情
        - 输入：patent_id USPTO 专利号（如 11234567）
        - 输出：PatentResult 专利详情
        - 异常：NotFoundError 未找到专利时抛出

    search_by_assignee(org_name: str, per_page: int = 10) -> SearchResponse
        - 功能：按受让人/申请人组织名检索
        - 输入：org_name 组织名称，per_page 分页大小
        - 输出：SearchResponse 搜索结果

    search_by_inventor(inventor_name: str, per_page: int = 10) -> SearchResponse
        - 功能：按发明人姓名检索
        - 输入：inventor_name 发明人姓名，per_page 分页大小
        - 输出：SearchResponse 搜索结果

    _parse_json(resp: httpx.Response) -> dict(静态方法)
        - 功能：安全解析 HTTP JSON 响应
        - 异常：ParseError JSON 格式错误时抛出

    _to_patent_result(raw: dict) -> PatentResult（静态方法）
        - 功能：将 PatentsView API 原始数据转换为统一的 PatentResult 模型

模块依赖：
    - httpx: HTTP 异步客户端
    - souwen.models: 统一数据模型
    - souwen.rate_limiter: 限流控制
    - souwen._parsing: 安全日期解析
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from souwen._parsing import safe_parse_date
from souwen.exceptions import NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

# PatentsView API 默认返回字段（包含分页、排序等关键信息）
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
        """初始化 PatentsView 客户端

        PatentsView 无需 API Key，直接初始化 HTTP 客户端和限流器。
        """
        self._http = SouWenHttpClient(base_url=self.BASE_URL, source_name="patentsview")
        # 45 req/min 限制，约 0.75 req/s
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

        # 逐项转换为标准 PatentResult
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
        # 使用精确匹配查询单个专利
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
        # 使用 _contains 进行模糊匹配组织名
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
        # 使用 _or 同时匹配名和姓
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
        """将 PatentsView 原始数据转换为 PatentResult 模型

        处理受让人、发明人、分类号等多种数据格式的转换。
        """
        # 受让人列表（可能为空）
        applicants: list[Applicant] = []
        for a in raw.get("assignees", []) or []:
            # 优先使用组织名，否则拼接姓名
            name = (
                a.get("assignee_organization")
                or f"{a.get('assignee_first_name', '')} {a.get('assignee_last_name', '')}".strip()
            )
            if name:
                applicants.append(Applicant(name=name, country=a.get("assignee_country")))

        # 发明人列表
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            # 拼接姓名
            full = (
                f"{inv.get('inventor_first_name', '')} {inv.get('inventor_last_name', '')}".strip()
            )
            if full:
                inventors.append(full)

        # CPC / IPC 分类号列表
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
            publication_date=safe_parse_date(raw.get("patent_date")),
            filing_date=safe_parse_date(raw.get("application_filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("patent_abstract"),
            cpc_codes=cpc_codes,
            ipc_codes=ipc_codes,
            source_url=f"https://search.patentsview.org/patent/{patent_id}",
            raw=raw,
        )
