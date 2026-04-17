"""PatSnap API 客户端

全球专利商业数据库，API Key 鉴权。
注册地址: https://connect.patsnap.com/
覆盖: 172 个司法管辖区，2 亿+ 专利

文件用途：
    PatSnap API 客户端实现，访问全球专利数据库。
    支持专利搜索、详情查询等基础功能。
    使用 API Key 鉴权，集成限流控制。

函数/类清单：
    PatSnapClient（类）
        - 功能：PatSnap API 客户端，管理 API Key 和请求
        - 关键属性：BASE_URL (str) API 基础地址
        - 关键变量：_api_key (str) API 凭证，_http (SouWenHttpClient) HTTP 客户端，_limiter 速率限制器

    search(query: str, limit: int = 10, offset: int = 0) -> SearchResponse
        - 功能：搜索全球专利
        - 输入：query 检索关键词或表达式，limit 返回数量，offset 偏移量
        - 输出：SearchResponse 包含总数和搜索结果

    get_patent(patent_id: str) -> PatentResult
        - 功能：获取单项专利详情
        - 输入：patent_id 专利号/公开号
        - 输出：PatentResult 专利详情
        - 异常：NotFoundError 专利不存在时抛出

    _parse_json(resp: httpx.Response) -> dict(静态方法)
        - 功能：安全解析 HTTP JSON 响应
        - 异常：ParseError JSON 格式错误时抛出

    _to_patent_result(raw: dict) -> PatentResult（静态方法）
        - 功能：将 PatSnap API 原始数据转换为统一的 PatentResult 模型

模块依赖：
    - httpx: HTTP 异步客户端
    - souwen.config: 配置管理（读取 API Key）
    - souwen.models: 统一数据模型
    - souwen.rate_limiter: 限流控制
    - souwen.exceptions: 异常类
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)


class PatSnapClient:
    """PatSnap API 客户端

    访问 PatSnap 全球专利数据库，覆盖 172 个司法管辖区。
    新账户免费 10,000 Credits。

    Attributes:
        BASE_URL: PatSnap Connect API 基础地址
    """

    BASE_URL = "https://connect.patsnap.com/open/api"

    def __init__(self) -> None:
        """初始化 PatSnap 客户端

        从配置读取 API Key，建立 HTTP 连接和限流控制。

        Raises:
            ConfigError: 缺少 API Key 时抛出
        """
        cfg = get_config()
        if not cfg.patsnap_api_key:
            raise ConfigError(
                key="patsnap_api_key",
                service="PatSnap",
                register_url="https://connect.patsnap.com/",
            )
        self._api_key = cfg.patsnap_api_key
        self._http = SouWenHttpClient(
            base_url=self.BASE_URL,
            headers={"X-PatSnap-Key": self._api_key},
            source_name="patsnap",
        )
        # 保守限流，避免信用额度消耗过快
        self._limiter = TokenBucketLimiter(rate=2.0, burst=5)

    async def __aenter__(self) -> PatSnapClient:
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
        limit: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索全球专利

        Args:
            query: 检索关键词或表达式
            limit: 返回结果数
            offset: 偏移量

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()
        resp = await self._http.post(
            "/patent/search",
            json={
                "q": query,
                "limit": limit,
                "offset": offset,
            },
        )
        data = self._parse_json(resp)

        # API 响应可能使用 results 或 patents 字段
        results_raw = data.get("results", data.get("patents", []))
        # 逐项转换为标准 PatentResult
        patents = [self._to_patent_result(item) for item in results_raw]

        return SearchResponse(
            query=query,
            source=SourceType.PATSNAP,
            total_results=data.get("total", data.get("totalCount")),
            results=patents,
            page=(offset // limit) + 1 if limit else 1,
            per_page=limit,
        )

    async def get_patent(self, patent_id: str) -> PatentResult:
        """获取专利详情

        Args:
            patent_id: 专利号 / 公开号

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/patent/{patent_id}",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {patent_id} 未找到")

        data = self._parse_json(resp)
        # API 可能返回顶级数据或嵌套在 data 字段
        result_data = data.get("data", data)
        if not result_data:
            raise NotFoundError(f"专利 {patent_id} 未找到")
        return self._to_patent_result(result_data)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"PatSnap 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 PatSnap 原始数据转换为 PatentResult

        处理多种数据格式和字段名变体（英文/中文）。
        """
        # 兼容多种字段名
        patent_id = raw.get(
            "publication_number",
            raw.get("patentNumber", raw.get("pn", "")),
        )

        # 申请人处理：支持字符串或对象列表
        applicants: list[Applicant] = []
        for a in raw.get("applicants", raw.get("assignees", [])) or []:
            if isinstance(a, str):
                applicants.append(Applicant(name=a))
            elif isinstance(a, dict):
                # 优先使用原始名或组织名
                name = a.get("name", a.get("original_name", ""))
                if name:
                    applicants.append(Applicant(name=name, country=a.get("country")))

        # 发明人处理
        inventors: list[str] = []
        for inv in raw.get("inventors", []) or []:
            name = inv if isinstance(inv, str) else inv.get("name", "")
            if name:
                inventors.append(name)

        # 分类号：支持字符串或对象列表
        ipc_codes: list[str] = [
            c if isinstance(c, str) else c.get("code", "")
            for c in (raw.get("ipc_codes", raw.get("ipc", [])) or [])
        ]
        cpc_codes: list[str] = [
            c if isinstance(c, str) else c.get("code", "")
            for c in (raw.get("cpc_codes", raw.get("cpc", [])) or [])
        ]

        return PatentResult(
            source=SourceType.PATSNAP,
            title=raw.get("title", raw.get("invention_title", "")),
            patent_id=patent_id,
            application_number=raw.get("application_number"),
            publication_date=_safe_date(raw.get("publication_date")),
            filing_date=_safe_date(raw.get("filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract"),
            claims=raw.get("claims"),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            family_id=raw.get("family_id"),
            legal_status=raw.get("legal_status"),
            source_url=f"https://connect.patsnap.com/patent/{patent_id}" if patent_id else "",
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
