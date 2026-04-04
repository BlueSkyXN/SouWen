"""The Lens API 客户端

专利 + 学术文献交叉引用检索，Bearer Token 鉴权。
注册地址: https://www.lens.org/lens/user/subscriptions
官方文档: https://docs.api.lens.org/
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError, RateLimitError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import SlidingWindowLimiter

logger = logging.getLogger(__name__)


class TheLensClient:
    """The Lens API 客户端

    支持专利与学术文献的联合检索和交叉引用分析。
    使用 Elasticsearch DSL 查询语法。

    限流信息来自响应头，动态更新：
    - ``x-rate-limit-remaining-request-per-minute``
    - ``x-rate-limit-retry-after-seconds``
    - ``x-rate-limit-remaining-request-per-month``

    Attributes:
        BASE_URL: The Lens API 基础地址
    """

    BASE_URL = "https://api.lens.org"

    def __init__(self) -> None:
        cfg = get_config()
        if not cfg.lens_api_token:
            raise ConfigError(
                key="lens_api_token",
                service="The Lens",
                register_url="https://www.lens.org/lens/user/subscriptions",
            )
        self._token = cfg.lens_api_token
        self._http = SouWenHttpClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        # 默认 10 req/min，通过响应头动态调整
        self._limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60.0)

    async def __aenter__(self) -> TheLensClient:
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

    async def search_patents(
        self,
        query: str | dict[str, Any],
        size: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索专利

        Args:
            query: Elasticsearch DSL 查询体或简单关键词。
                   若为字符串，自动构造 ``match`` 查询。
            size: 返回结果数
            offset: 偏移量

        Returns:
            SearchResponse 封装的搜索结果
        """
        body = self._build_query(query, size=size, offset=offset)
        data = await self._post_search("/patent/search", body)

        patents = [
            self._to_patent_result(item) for item in data.get("data", [])
        ]
        return SearchResponse(
            query=str(query),
            source=SourceType.THE_LENS,
            total_results=data.get("total"),
            results=patents,
            page=(offset // size) + 1 if size else 1,
            per_page=size,
        )

    async def search_scholarly(
        self,
        query: str | dict[str, Any],
        size: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """搜索学术文献

        Args:
            query: Elasticsearch DSL 查询体或简单关键词
            size: 返回结果数
            offset: 偏移量

        Returns:
            原始搜索结果字典（学术文献暂不转换为 PatentResult）
        """
        body = self._build_query(query, size=size, offset=offset)
        return await self._post_search("/scholarly/search", body)

    async def get_by_lens_id(self, lens_id: str) -> PatentResult:
        """根据 Lens ID 获取专利详情

        Args:
            lens_id: Lens 唯一标识符

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        body = {
            "query": {"term": {"lens_id": lens_id}},
            "size": 1,
        }
        data = await self._post_search("/patent/search", body)
        items = data.get("data", [])
        if not items:
            raise NotFoundError(f"Lens ID {lens_id} 未找到")
        return self._to_patent_result(items[0])

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _post_search(
        self, endpoint: str, body: dict[str, Any],
    ) -> dict[str, Any]:
        """发送搜索请求并处理限流"""
        await self._limiter.acquire()
        resp = await self._http.post(endpoint, json=body)

        # 从响应头更新限流信息
        self._update_rate_limit(resp)

        if resp.status_code == 429:
            retry_after = _safe_float(
                resp.headers.get("x-rate-limit-retry-after-seconds")
            )
            raise RateLimitError(
                message="The Lens 请求频率超限",
                retry_after=retry_after,
            )

        return self._parse_json(resp)

    def _update_rate_limit(self, resp: httpx.Response) -> None:
        """从响应头动态更新限流参数"""
        remaining = _safe_int(
            resp.headers.get("x-rate-limit-remaining-request-per-minute")
        )
        retry_after = _safe_float(
            resp.headers.get("x-rate-limit-retry-after-seconds")
        )
        self._limiter.update_from_headers(
            remaining=remaining, retry_after=retry_after,
        )

        # 记录月度剩余
        monthly = resp.headers.get("x-rate-limit-remaining-request-per-month")
        if monthly is not None:
            logger.debug("The Lens 月度剩余: %s", monthly)

    @staticmethod
    def _build_query(
        query: str | dict[str, Any],
        size: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """构造 Elasticsearch DSL 查询体"""
        if isinstance(query, str):
            es_query: dict[str, Any] = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "title",
                            "abstract",
                            "claims",
                            "description",
                        ],
                    },
                },
            }
        else:
            es_query = {"query": query} if "query" not in query else query

        es_query["size"] = size
        es_query["from"] = offset
        return es_query

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"The Lens 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 The Lens 原始数据转换为 PatentResult"""
        patent_id = raw.get(
            "doc_number",
            raw.get("publication_key", raw.get("lens_id", "")),
        )
        lens_id = raw.get("lens_id", "")

        # 申请人
        applicants: list[Applicant] = []
        for a in raw.get("applicants", []) or []:
            name = a if isinstance(a, str) else a.get("name", "")
            country = a.get("country") if isinstance(a, dict) else None
            if name:
                applicants.append(Applicant(name=name, country=country))

        # 发明人
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            name = inv if isinstance(inv, str) else inv.get("name", "")
            if name:
                inventors.append(name)

        # 分类号
        ipc_codes: list[str] = []
        for c in raw.get("ipc", raw.get("ipc_codes", [])) or []:
            code = c if isinstance(c, str) else c.get("code", "")
            if code:
                ipc_codes.append(code)

        cpc_codes: list[str] = []
        for c in raw.get("cpc", raw.get("cpc_codes", [])) or []:
            code = c if isinstance(c, str) else c.get("code", "")
            if code:
                cpc_codes.append(code)

        return PatentResult(
            source=SourceType.THE_LENS,
            title=raw.get("title", ""),
            patent_id=patent_id,
            application_number=raw.get("application_number"),
            publication_date=_safe_date(raw.get("date_published")),
            filing_date=_safe_date(raw.get("filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract"),
            claims=raw.get("claims"),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            family_id=raw.get("family_id"),
            legal_status=raw.get("legal_status"),
            source_url=f"https://www.lens.org/lens/patent/{lens_id}" if lens_id else "",
            raw=raw,
        )


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串"""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _safe_int(value: str | None) -> int | None:
    """安全转换整数"""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: str | None) -> float | None:
    """安全转换浮点数"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
