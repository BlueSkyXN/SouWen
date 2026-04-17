"""PQAI 语义专利检索客户端

基于自然语言的专利语义搜索，免费无需 API Key。
官方文档: https://projectpq.ai
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


class PqaiClient:
    """PQAI 语义专利检索客户端

    纯语义搜索引擎，支持自然语言查询，免费无需注册。

    Attributes:
        BASE_URL: PQAI API 基础地址
        RATE_LIMIT: 1000 次/小时 → 约 0.27 次/秒
    """

    BASE_URL = "https://api.projectpq.ai"
    RATE_LIMIT = 0.27  # ~1000 req/hour

    def __init__(self) -> None:
        self._http = SouWenHttpClient(base_url=self.BASE_URL, source_name="pqai")
        self._limiter = TokenBucketLimiter(rate=self.RATE_LIMIT, burst=5)

    async def __aenter__(self) -> PqaiClient:
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
        query: str,
        n_results: int = 10,
    ) -> SearchResponse:
        """语义搜索专利

        支持自然语言描述，例如：
        ``"method for detecting cancer using machine learning on MRI images"``

        Args:
            query: 自然语言查询或关键词
            n_results: 返回结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/search/102",
            params={"q": query, "n": n_results, "type": "patent"},
        )
        data = self._parse_json(resp)

        results = [self._to_patent_result(item) for item in data.get("results", [])]
        return SearchResponse(
            query=query,
            source=SourceType.PQAI,
            total_results=len(results),
            results=results,
            page=1,
            per_page=n_results,
        )

    async def similar_patents(
        self,
        patent_id: str,
        n_results: int = 10,
    ) -> SearchResponse:
        """查找相似专利

        Args:
            patent_id: 专利号，例如 ``"US11234567B2"``
            n_results: 返回结果数

        Returns:
            SearchResponse 封装的搜索结果

        Raises:
            NotFoundError: 指定专利不存在
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/similar/{patent_id}",
            params={"n": n_results, "type": "patent"},
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {patent_id} 未找到")
        data = self._parse_json(resp)

        results = [self._to_patent_result(item) for item in data.get("results", [])]
        return SearchResponse(
            query=f"similar:{patent_id}",
            source=SourceType.PQAI,
            total_results=len(results),
            results=results,
            page=1,
            per_page=n_results,
        )

    async def predict_cpc(self, text: str) -> list[dict[str, Any]]:
        """预测 CPC 分类号

        根据技术描述文本预测最可能的 CPC 分类号。

        Args:
            text: 技术描述文本

        Returns:
            CPC 分类预测列表，每项包含 ``code`` 和 ``score`` 等字段
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/classify/cpc",
            params={"q": text},
        )
        data = self._parse_json(resp)
        return data.get("predictions", [])

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"PQAI 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 PQAI 原始数据转换为 PatentResult"""
        patent_id = raw.get("id", raw.get("publication_number", ""))

        # PQAI 返回的申请人 / 发明人格式因版本而异
        applicants: list[Applicant] = []
        for name in raw.get("assignees", []) or []:
            if isinstance(name, str) and name.strip():
                applicants.append(Applicant(name=name.strip()))
            elif isinstance(name, dict):
                applicants.append(
                    Applicant(
                        name=name.get("name", ""),
                        country=name.get("country"),
                    )
                )

        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            if isinstance(inv, str) and inv.strip():
                inventors.append(inv.strip())
            elif isinstance(inv, dict):
                inventors.append(inv.get("name", ""))

        cpc_codes: list[str] = []
        for c in raw.get("cpcs", raw.get("cpc_codes", [])) or []:
            if isinstance(c, str):
                cpc_codes.append(c)
            elif isinstance(c, dict):
                cpc_codes.append(c.get("code", ""))

        pub_date = safe_parse_date(raw.get("publication_date"))

        return PatentResult(
            source=SourceType.PQAI,
            title=raw.get("title", ""),
            patent_id=patent_id,
            publication_date=pub_date,
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract"),
            cpc_codes=cpc_codes,
            source_url=f"https://patents.google.com/patent/{patent_id}",
            raw=raw,
        )
