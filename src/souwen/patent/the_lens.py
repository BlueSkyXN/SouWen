"""The Lens API 客户端

专利 + 学术文献交叉引用检索，Bearer Token 鉴权。
注册地址: https://www.lens.org/lens/user/subscriptions
官方文档: https://docs.api.lens.org/

文件用途：
    The Lens API 客户端，提供专利与学术文献的联合检索。
    支持复杂的 Elasticsearch DSL 查询语法。
    集成动态限流控制，根据响应头实时更新限流参数。

函数/类清单：
    TheLensClient（类）
        - 功能：The Lens API 客户端，管理 Bearer Token 连接和限流
        - 关键属性：BASE_URL (str) API 基础地址
        - 关键变量：_token (str) API 令牌，_http (SouWenHttpClient) HTTP 客户端，_limiter 限流器
    
    search_patents(query: str | dict, size: int = 10, offset: int = 0) -> SearchResponse
        - 功能：搜索专利（支持 Elasticsearch DSL 查询）
        - 输入：query 关键词或 ES DSL 查询体，size 返回数量，offset 偏移量
        - 输出：SearchResponse 包含搜索结果
    
    search_scholarly(query: str | dict, size: int = 10, offset: int = 0) -> dict
        - 功能：搜索学术文献（返回原始响应）
        - 输入：query 关键词或 ES DSL 查询体，size 返回数量，offset 偏移量
        - 输出：原始搜索结果字典
    
    get_by_lens_id(lens_id: str) -> PatentResult
        - 功能：根据 Lens ID 获取专利详情
        - 输入：lens_id Lens 唯一标识符
        - 输出：PatentResult 专利详情
        - 异常：NotFoundError Lens ID 不存在时抛出
    
    _build_query(query: str | dict, size: int = 10, offset: int = 0) -> dict（静态方法）
        - 功能：构造 Elasticsearch DSL 查询体
        - 处理字符串和对象格式的查询
    
    _parse_json(resp: httpx.Response) -> dict(静态方法)
        - 功能：安全解析 HTTP JSON 响应
        - 异常：ParseError JSON 格式错误时抛出
    
    _to_patent_result(raw: dict) -> PatentResult（静态方法）
        - 功能：将 The Lens 原始数据转换为统一的 PatentResult 模型

模块依赖：
    - httpx: HTTP 异步客户端
    - souwen.config: 配置管理（读取 API 令牌）
    - souwen.models: 统一数据模型
    - souwen.rate_limiter: 限流控制（支持动态更新）
    - souwen.exceptions: 异常类（RateLimitError）
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
        """初始化 The Lens 客户端
        
        从配置读取 Bearer Token，建立连接和限流控制。
        
        Raises:
            ConfigError: 缺少 API Token 时抛出
        """
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
            source_name="the_lens",
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
        # 发送搜索请求，自动处理限流和错误
        data = await self._post_search("/patent/search", body)

        # 逐项转换为标准 PatentResult
        patents = [self._to_patent_result(item) for item in data.get("data", [])]
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
        # 调用学术文献专用端点，返回原始响应
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
        # 使用 term 查询精确匹配 lens_id
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
        self,
        endpoint: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """发送搜索请求并处理限流和错误
        
        自动从响应头提取限流信息并动态更新限制器。
        """
        await self._limiter.acquire()
        resp = await self._http.post(endpoint, json=body)

        # 从响应头更新限流信息
        self._update_rate_limit(resp)

        # 429 表示请求频率超限
        if resp.status_code == 429:
            retry_after = _safe_float(resp.headers.get("x-rate-limit-retry-after-seconds"))
            raise RateLimitError(
                message="The Lens 请求频率超限",
                retry_after=retry_after,
            )

        return self._parse_json(resp)

    def _update_rate_limit(self, resp: httpx.Response) -> None:
        """从响应头动态更新限流参数
        
        根据 API 返回的剩余配额和重试时间，实时调整限流器参数。
        """
        remaining = _safe_int(resp.headers.get("x-rate-limit-remaining-request-per-minute"))
        retry_after = _safe_float(resp.headers.get("x-rate-limit-retry-after-seconds"))
        self._limiter.update_from_headers(
            remaining=remaining,
            retry_after=retry_after,
        )

        # 记录月度剩余配额（仅用于监控，不影响限流）
        monthly = resp.headers.get("x-rate-limit-remaining-request-per-month")
        if monthly is not None:
            logger.debug("The Lens 月度剩余: %s", monthly)

    @staticmethod
    def _build_query(
        query: str | dict[str, Any],
        size: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """构造 Elasticsearch DSL 查询体
        
        如果输入是字符串，自动构造 multi_match 查询（跨多个字段）。
        如果是对象，直接使用或嵌入到 query 字段。
        """
        if isinstance(query, str):
            # 简单字符串查询，转换为 multi_match（同时搜索标题、摘要、权利要求等）
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
            # 对象查询，检查是否已包含 query 字段
            es_query = {"query": query} if "query" not in query else query

        es_query["size"] = size
        es_query["from"] = offset
        return es_query

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """安全解析 JSON 响应
        
        Raises:
            ParseError: JSON 格式错误时抛出
        """
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"The Lens 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 The Lens 原始数据转换为统一 PatentResult 模型
        
        Lens API 返回的字段包括：doc_number（国家代码-号码），publication_key，lens_id 等。
        申请人和发明人可能是字符串列表或对象列表，需要容错处理。
        分类号同样支持多种格式（IPC/CPC）。
        """
        # 专利号优先级：doc_number > publication_key > lens_id
        patent_id = raw.get(
            "doc_number",
            raw.get("publication_key", raw.get("lens_id", "")),
        )
        lens_id = raw.get("lens_id", "")

        # 申请人：处理字符串或对象（含国家信息）
        applicants: list[Applicant] = []
        for a in raw.get("applicants", []) or []:
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

        # IPC 分类号：支持 ipc/ipc_codes 两种字段名，每项可能是字符串或对象
        ipc_codes: list[str] = []
        for c in raw.get("ipc", raw.get("ipc_codes", [])) or []:
            code = c if isinstance(c, str) else c.get("code", "")
            if code:
                ipc_codes.append(code)

        # CPC 分类号：同样支持多种格式
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
    """安全解析日期字符串
    
    支持 ISO 8601 格式（YYYY-MM-DD），取前 10 字符处理。
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _safe_int(value: str | None) -> int | None:
    """安全转换整数字符串
    
    用于解析限流响应头中的整数值。
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: str | None) -> float | None:
    """安全转换浮点数字符串
    
    用于解析限流响应头中的延迟秒数（可能是浮点数）。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
