"""CNIPA 中国国家知识产权局客户端

通过中国专利信息中心 (CNIPR) 开放平台访问中国专利数据，OAuth 2.0 鉴权。
注册地址: https://open.cnipr.com/

文件用途：
    CNIPA 客户端实现，提供中国专利搜索、详情查询、全文获取等功能。
    使用 OAuth 2.0 Client Credentials 鉴权方式，集成限流控制。

函数/类清单：
    CnipaClient（类）
        - 功能：CNIPA 专利数据客户端，管理 OAuth 连接和 API 请求
        - 关键属性：BASE_URL (str) API 基础地址，TOKEN_URL (str) OAuth 令牌端点
        - 关键变量：_http (OAuthClient) OAuth HTTP 客户端，_limiter (TokenBucketLimiter) 速率限制器

    search(query: str, per_page: int = 10, offset: int = 0) -> SearchResponse
        - 功能：按关键词搜索中国专利，支持 CNIPA 检索语法
        - 输入：query 检索表达式，per_page 每页结果数，offset 偏移量
        - 输出：SearchResponse 包含总数、专利列表、分页信息

    get_patent(publication_number: str) -> PatentResult
        - 功能：根据公开号获取单项专利详情
        - 输入：publication_number 公开号（如 CN115000000A）
        - 输出：PatentResult 专利详情模型
        - 异常：NotFoundError 专利不存在时抛出

    get_fulltext(publication_number: str) -> dict[str, Any]
        - 功能：获取专利全文（说明书、权利要求书等）
        - 输入：publication_number 公开号
        - 输出：包含全文内容的字典
        - 异常：NotFoundError 全文不可用时抛出

    _parse_json(resp: httpx.Response) -> dict[str, Any]（静态方法）
        - 功能：安全解析 HTTP JSON 响应
        - 输入：resp httpx 响应对象
        - 输出：解析后的字典
        - 异常：ParseError JSON 格式错误时抛出

    _to_patent_result(raw: dict[str, Any]) -> PatentResult（静态方法）
        - 功能：将 CNIPA API 原始数据转换为统一的 PatentResult 模型
        - 输入：raw CNIPA API 返回的原始数据字典
        - 输出：标准化的 PatentResult 对象

模块依赖：
    - httpx: HTTP 异步客户端
    - souwen.core.http_client: OAuth 连接管理
    - souwen.models: 统一数据模型（PatentResult, SearchResponse 等）
    - souwen.core.rate_limiter: 限流控制（令牌桶算法）
    - souwen.config: 配置管理（读取 API 凭证）
    - souwen.core.exceptions: 异常类
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.config import get_config
from souwen.core.exceptions import ConfigError, NotFoundError, ParseError
from souwen.core.http_client import OAuthClient
from souwen.models import Applicant, PatentResult, SearchResponse
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)


class CnipaClient:
    """CNIPA 中国国家知识产权局客户端

    访问中国专利全文数据，支持检索、详情、全文获取。
    使用 OAuth 2.0 Client Credentials 鉴权。

    Attributes:
        BASE_URL: CNIPR 开放平台基础地址
        TOKEN_URL: OAuth 2.0 令牌端点
    """

    BASE_URL = "https://open.cnipr.com"
    TOKEN_URL = "https://open.cnipr.com/oauth/token"

    def __init__(self) -> None:
        """初始化 CNIPA 客户端

        从配置读取 OAuth 凭证，建立 OAuth 连接和限流控制。

        Raises:
            ConfigError: 缺少必要的 OAuth 凭证时抛出
        """
        cfg = get_config()
        client_id = cfg.resolve_api_key("cnipa", "cnipa_client_id")
        client_secret = cfg.cnipa_client_secret
        if not client_id or not client_secret:
            raise ConfigError(
                key="cnipa_client_id / cnipa_client_secret",
                service="CNIPA (CNIPR 开放平台)",
                register_url="https://open.cnipr.com/",
            )
        # 初始化 OAuth 客户端，自动处理令牌获取和刷新
        self._http = OAuthClient(
            base_url=self.BASE_URL,
            token_url=self.TOKEN_URL,
            client_id=client_id,
            client_secret=client_secret,
            source_name="cnipa",
        )
        # 限流：2 请求/秒，突增容量 5 请求
        self._limiter = TokenBucketLimiter(rate=2.0, burst=5)

    async def __aenter__(self) -> CnipaClient:
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
        per_page: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索中国专利

        Args:
            query: 检索表达式 (支持 CNIPA 检索语法)
            per_page: 每页结果数
            offset: 偏移量

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()  # 获取限流令牌
        resp = await self._http.get(
            "/api/search",
            params={
                "q": query,
                "rows": per_page,
                "start": offset,
            },
        )
        data = self._parse_json(resp)

        # API 响应可能使用 results 或 data 字段
        results_raw = data.get("results", data.get("data", []))
        # 转换每条原始数据为标准 PatentResult 模型
        patents = [self._to_patent_result(item) for item in results_raw]

        return SearchResponse(
            query=query,
            source="cnipa",
            total_results=data.get("total", data.get("totalCount")),
            results=patents,
            page=(offset // per_page) + 1 if per_page else 1,
            per_page=per_page,
        )

    async def get_patent(self, publication_number: str) -> PatentResult:
        """获取专利详情

        Args:
            publication_number: 公开号，例如 ``"CN115000000A"``

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/api/patent/{publication_number}",
        )
        # 404 表示专利不存在
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {publication_number} 未找到")

        data = self._parse_json(resp)
        # API 可能返回顶级数据或嵌套在 data 字段
        result_data = data.get("data", data)
        if not result_data:
            raise NotFoundError(f"专利 {publication_number} 未找到")
        return self._to_patent_result(result_data)

    async def get_fulltext(self, publication_number: str) -> dict[str, Any]:
        """获取专利全文

        Args:
            publication_number: 公开号

        Returns:
            包含说明书、权利要求书等全文内容的字典

        Raises:
            NotFoundError: 未找到该专利全文
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/api/patent/{publication_number}/fulltext",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {publication_number} 全文未找到")

        data = self._parse_json(resp)
        return data.get("data", data)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"CNIPA 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 CNIPA 原始数据转换为 PatentResult

        处理多种数据格式（驼峰命名、蛇形命名、中文字段），保证数据兼容性。
        """
        # 兼容多种字段名（publicationNumber, publication_number, pn）
        patent_id = raw.get(
            "publicationNumber",
            raw.get("publication_number", raw.get("pn", "")),
        )
        app_number = raw.get(
            "applicationNumber",
            raw.get("application_number", raw.get("an")),
        )

        # 申请人处理：支持字符串列表或对象列表，中文数据可能以分号分隔
        applicants: list[Applicant] = []
        raw_applicants = raw.get("applicants", raw.get("申请人", []))
        if isinstance(raw_applicants, str):
            # 中文数据源有时以分号分隔
            raw_applicants = [a.strip() for a in raw_applicants.split(";") if a.strip()]
        for a in raw_applicants or []:
            name = a if isinstance(a, str) else a.get("name", a.get("姓名", ""))
            country = a.get("country") if isinstance(a, dict) else None
            if name:
                applicants.append(Applicant(name=name, country=country))

        # 发明人处理：类似申请人，支持字符串或对象格式
        raw_inventors = raw.get("inventors", raw.get("发明人", []))
        inventors: list[str] = []
        if isinstance(raw_inventors, str):
            inventors = [i.strip() for i in raw_inventors.split(";") if i.strip()]
        else:
            for inv in raw_inventors or []:
                name = inv if isinstance(inv, str) else inv.get("name", "")
                if name:
                    inventors.append(name)

        # IPC 分类号：可能为字符串（分号分隔）或列表
        ipc_raw = raw.get("ipcCodes", raw.get("ipc", []))
        ipc_codes: list[str] = (
            [i.strip() for i in ipc_raw.split(";") if i.strip()]
            if isinstance(ipc_raw, str)
            else [c for c in ipc_raw if isinstance(c, str)]
        )

        # CPC 分类号：处理方式同 IPC
        cpc_raw = raw.get("cpcCodes", raw.get("cpc", []))
        cpc_codes: list[str] = (
            [c.strip() for c in cpc_raw.split(";") if c.strip()]
            if isinstance(cpc_raw, str)
            else [c for c in cpc_raw if isinstance(c, str)]
        )

        return PatentResult(
            source="cnipa",
            title=raw.get("title", raw.get("发明名称", "")),
            patent_id=patent_id,
            application_number=app_number,
            publication_date=_safe_date(raw.get("publicationDate", raw.get("publication_date"))),
            filing_date=_safe_date(raw.get("filingDate", raw.get("filing_date"))),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract", raw.get("摘要")),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            legal_status=raw.get("legalStatus", raw.get("legal_status")),
            source_url=f"https://open.cnipr.com/patent/{patent_id}" if patent_id else "",
            raw=raw,
        )


def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串

    处理 ISO 8601 格式日期（YYYY-MM-DD），截取前 10 字符以兼容时间戳格式。

    Args:
        value: 日期字符串或 None

    Returns:
        date 对象，解析失败返回 None
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
