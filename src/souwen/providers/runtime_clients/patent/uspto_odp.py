"""USPTO Open Data Portal (ODP) 客户端"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.config import get_config
from souwen.common_runtime.provider_support.exceptions import ConfigError, NotFoundError, ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.providers.runtime_clients.models import Applicant, PatentResult, SearchResponse
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)


class UsptoOdpClient:
    """USPTO Open Data Portal 客户端

    访问 USPTO 开放数据门户，支持专利申请、转让、PTAB 等数据。
    需要 API Key (通过 ``X-API-Key`` 请求头传递)。

    Attributes:
        BASE_URL: USPTO ODP API 基础地址
    """

    BASE_URL = "https://data.uspto.gov/api/v1"

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 USPTO ODP 客户端

        从配置读取 API Key，建立连接和限流控制。
        默认限流 5 req/s（保守估计，基于 5M req/week ≈ 8.3 req/s）。

        Raises:
            ConfigError: 缺少 API Key 时抛出
        """
        cfg = get_config()
        api_key = api_key or cfg.resolve_api_key("uspto_odp", "uspto_api_key")
        if not api_key:
            raise ConfigError(
                key="uspto_api_key",
                service="USPTO Open Data Portal",
                register_url="https://data.uspto.gov/",
            )
        self._api_key = api_key
        self._http = SouWenHttpClient(
            base_url=self.BASE_URL,
            headers={"X-API-Key": self._api_key},
            source_name="uspto_odp",
        )
        # 5M req/week ≈ ~8.3 req/s，保守设为 5 req/s，突发 10 req
        self._limiter = TokenBucketLimiter(rate=5.0, burst=10)

    async def __aenter__(self) -> UsptoOdpClient:
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

    async def search_applications(
        self,
        query: str,
        per_page: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索专利申请

        Args:
            query: 搜索关键词
            per_page: 每页结果数
            offset: 偏移量

        Returns:
            SearchResponse 封装的搜索结果（自动转换为 PatentResult）

        说明：
            响应体中可能包含 results 或 patents 两种字段，取决于 API 版本。
            同样，总数字段可能是 recordTotalQuantity 或 totalCount。
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/patent/applications",
            params={
                "q": query,
                "rows": per_page,
                "start": offset,
            },
        )
        data = self._parse_json(resp)

        # 容错处理：支持 results 或 patents 两种字段名
        results_raw = data.get("results", data.get("patents", []))
        patents = [self._to_patent_result(item) for item in results_raw]

        return SearchResponse(
            query=query,
            source="uspto_odp",
            total_results=data.get("recordTotalQuantity", data.get("totalCount")),
            results=patents,
            page=(offset // per_page) + 1 if per_page else 1,
            per_page=per_page,
        )

    async def get_transactions(
        self,
        app_number: str,
    ) -> list[dict[str, Any]]:
        """获取申请事务历史

        记录申请的重要日期和状态变更，例如：
        - 申请受理日期
        - 审查意见发出日期
        - 驳回或授权日期
        等。

        Args:
            app_number: 申请号

        Returns:
            事务记录列表，每项为原始字典（不转换为 PatentResult）

        Raises:
            NotFoundError: 未找到该申请
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/patent/applications/{app_number}/transactions",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"申请 {app_number} 未找到")
        data = self._parse_json(resp)
        # 支持 transactions 或 results 两种字段名
        return data.get("transactions", data.get("results", []))

    async def get_assignments(
        self,
        patent_id: str,
    ) -> list[dict[str, Any]]:
        """获取专利转让/所有权变更记录

        查询专利的转让、抵押、许可等权益变更历史。

        Args:
            patent_id: 专利号

        Returns:
            转让记录列表，每项为原始字典
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/patent/assignments",
            params={"patentNumber": patent_id},
        )
        data = self._parse_json(resp)
        # 支持 assignments 或 results 两种字段名
        return data.get("assignments", data.get("results", []))

    async def get_ptab_decisions(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        """获取 PTAB 审判决定

        PTAB（Patent Trial and Appeal Board）是美国专利的再审和上诉机构。
        此方法查询与给定案件号或关键词相关的审判决定。

        Args:
            query: 搜索关键词或案件号

        Returns:
            PTAB 决定记录列表，每项为原始字典
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/patent/ptab",
            params={"q": query},
        )
        data = self._parse_json(resp)
        return data.get("results", [])

    async def get_office_actions(
        self,
        app_number: str,
    ) -> list[dict[str, Any]]:
        """获取审查意见通知书 (Office Actions)

        Office Actions 是 USPTO 审查员在审查过程中向申请人发出的通知，
        包括驳回理由、申请人答辩期限等重要信息。

        Args:
            app_number: 申请号

        Returns:
            审查意见列表，每项为原始字典

        Raises:
            NotFoundError: 未找到该申请
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/patent/applications/{app_number}/office-actions",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"申请 {app_number} 的审查意见未找到")
        data = self._parse_json(resp)
        # 支持 officeActions 或 results 两种字段名
        return data.get("officeActions", data.get("results", []))

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """安全解析 JSON 响应

        Raises:
            ParseError: JSON 格式错误时抛出
        """
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"USPTO ODP 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 USPTO ODP 原始数据转换为统一 PatentResult 模型

        仅在 search_applications 中使用。
        USPTO ODP 的专利号可能在多个字段中，优先级为：
        patentNumber > publicationNumber > applicationNumber

        申请人可能在 applicants 或 assignees 字段中（对象或字符串）。
        日期字段采用 ISO 8601 格式（YYYY-MM-DD）。
        """
        # 专利号优先级
        patent_id = raw.get(
            "patentNumber",
            raw.get("publicationNumber", raw.get("applicationNumber", "")),
        )
        app_number = raw.get("applicationNumber")

        # 申请人：处理字符串或对象
        applicants: list[Applicant] = []
        for a in raw.get("applicants", raw.get("assignees", [])) or []:
            name = a if isinstance(a, str) else a.get("name", "")
            country = a.get("country") if isinstance(a, dict) else None
            if name:
                applicants.append(Applicant(name=name, country=country))

        # 发明人：处理字符串或对象
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            name = inv if isinstance(inv, str) else inv.get("name", "")
            if name:
                inventors.append(name)

        # 分类号：直接提取字符串列表
        ipc_codes: list[str] = [c for c in (raw.get("ipcCodes", []) or []) if isinstance(c, str)]
        cpc_codes: list[str] = [c for c in (raw.get("cpcCodes", []) or []) if isinstance(c, str)]

        return PatentResult(
            source="uspto_odp",
            title=raw.get("inventionTitle", raw.get("title", "")),
            patent_id=patent_id,
            application_number=app_number,
            publication_date=_safe_date(raw.get("publicationDate")),
            filing_date=_safe_date(raw.get("filingDate")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract"),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            source_url=f"https://data.uspto.gov/patent/{patent_id}" if patent_id else "",
            raw=raw,
        )


def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串

    支持 ISO 8601 格式（YYYY-MM-DD），取前 10 字符处理。
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
