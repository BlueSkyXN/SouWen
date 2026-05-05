"""PQAI 语义专利检索客户端

基于自然语言的专利语义搜索，免费无需 API Key。
官方文档: https://projectpq.ai

文件用途：
    PQAI 纯语义搜索客户端，支持自然语言查询和相似专利查询。
    无需注册即可使用，提供 CPC 分类预测功能。
    适合发现相关专利、进行技术领域分析。

函数/类清单：
    PqaiClient（类）
        - 功能：PQAI 语义搜索客户端，管理 HTTP 连接和速率限制
        - 关键属性：BASE_URL (str) API 基础地址，RATE_LIMIT (float) 限流速率
        - 关键变量：_http (SouWenHttpClient) HTTP 客户端，_limiter 速率限制器

    search(query: str, n_results: int = 10) -> SearchResponse
        - 功能：语义搜索专利（支持自然语言描述）
        - 输入：query 自然语言查询或关键词，n_results 返回结果数
        - 输出：SearchResponse 包含搜索结果
        - 示例查询：「method for detecting cancer using machine learning on MRI images」

    similar_patents(patent_id: str, n_results: int = 10) -> SearchResponse
        - 功能：查找相似专利
        - 输入：patent_id 专利号（如 US11234567B2），n_results 返回数量
        - 输出：SearchResponse 相似专利列表
        - 异常：NotFoundError 指定专利不存在时抛出

    predict_cpc(text: str) -> list[dict[str, Any]]
        - 功能：预测 CPC 分类号（基于技术描述文本）
        - 输入：text 技术描述文本
        - 输出：CPC 分类预测列表，每项包含 code 和 score 等字段

    _parse_json(resp: httpx.Response) -> dict(静态方法)
        - 功能：安全解析 HTTP JSON 响应
        - 异常：ParseError JSON 格式错误时抛出

    _to_patent_result(raw: dict) -> PatentResult（静态方法）
        - 功能：将 PQAI 原始数据转换为统一的 PatentResult 模型

模块依赖：
    - httpx: HTTP 异步客户端
    - souwen.models: 统一数据模型
    - souwen.core.rate_limiter: 限流控制
    - souwen.core.parsing: 安全日期解析
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from souwen.core.parsing import safe_parse_date
from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.core.rate_limiter import TokenBucketLimiter

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
        """初始化 PQAI 客户端

        无需 API Key，直接初始化 HTTP 客户端和限流器。
        """
        self._http = SouWenHttpClient(base_url=self.BASE_URL, source_name="pqai")
        # 1000 req/hour 限制，约 0.27 req/s
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

        # 逐项转换为标准 PatentResult
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
        # 404 表示专利不存在
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {patent_id} 未找到")
        data = self._parse_json(resp)

        # 逐项转换为标准 PatentResult
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
        """将 PQAI 原始数据转换为 PatentResult

        处理多种数据格式（字符串或对象），PQAI 格式因版本而异。
        """
        patent_id = raw.get("id", raw.get("publication_number", ""))

        # 申请人处理：PQAI 返回格式因版本而异，可能是字符串列表或对象列表
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

        # 发明人处理：类似申请人
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            if isinstance(inv, str) and inv.strip():
                inventors.append(inv.strip())
            elif isinstance(inv, dict):
                inventors.append(inv.get("name", ""))

        # CPC 分类号：支持字符串或对象列表
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
