"""智谱 AI Web Search Pro 搜索 API 客户端

文件用途：
    智谱 AI 网络搜索客户端。调用智谱 AI 平台的 web-search-pro 工具（非 MCP 版），
    通过 REST API 直接获取带摘要的网页搜索结果。
    支持域名过滤、时间范围过滤、摘要长度控制和自定义引擎。

函数/类清单：
    ZhipuAISearchClient（类）
        - 功能：调用 `https://open.bigmodel.cn/api/paas/v4/tools` 的 web-search-pro 工具
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "zhipuai", BASE_URL = "https://open.bigmodel.cn",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse

    ZhipuAISearchClient.__init__(api_key=None)
        - 功能：初始化客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_ZHIPUAI_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ZhipuAISearchClient.search(query, max_results, search_engine, search_domain_filter,
                               search_recency_filter, content_size) -> WebSearchResponse
        - 功能：通过智谱 AI web-search-pro 执行网页搜索
        - 输入：query 搜索词, max_results 最大结果数（1-50），
                search_engine 搜索引擎（默认 search_pro），
                search_domain_filter 域名过滤（可选），
                search_recency_filter 时间范围过滤（noLimit/day/week/month/year），
                content_size 摘要长度控制（low/medium/high）
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：POST /api/paas/v4/tools，Authorization: Bearer <api_key>
    - 工具名称：web-search-pro，消息格式兼容 OpenAI chat 消息体
    - 响应解析：choices[0].message.tool_calls[*].search_result 数组
    - 每条结果含 title、link、content（摘要）、icon、media 字段
    - 最多返回 50 条结果（API 上限）
    - 支持时间范围过滤（搜索最近一天/周/月/年内的内容）
    - 支持 content_size 控制摘要长度（low/medium/high）
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.zhipuai_search")

_VALID_RECENCY = {"noLimit", "day", "week", "month", "year"}
_VALID_CONTENT_SIZES = {"low", "medium", "high"}


class ZhipuAISearchClient(SouWenHttpClient):
    """智谱 AI Web Search Pro 搜索客户端

    调用智谱 AI 平台的 web-search-pro 工具 API，无需通过 MCP，
    直接通过 REST API 获取带摘要的中英文网页搜索结果。

    特色功能：
    - AI 摘要提取：每条结果附带智谱提炼的内容摘要（content 字段）
    - 域名过滤：可限定搜索范围至指定域名
    - 时间范围过滤：可限定搜索最近一天/周/月/年内的内容
    - 摘要长度控制：low（简短）/ medium（适中）/ high（详细）

    Args:
        api_key: 智谱 AI API Key，默认从 SOUWEN_ZHIPUAI_API_KEY 读取
    """

    ENGINE_NAME = "zhipuai"
    BASE_URL = "https://open.bigmodel.cn"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("zhipuai", "zhipuai_api_key")
        if not self.api_key:
            raise ConfigError(
                "zhipuai_api_key",
                "ZhipuAI",
                "https://open.bigmodel.cn/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="zhipuai")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_engine: str = "search_pro",
        search_domain_filter: str | None = None,
        search_recency_filter: str = "noLimit",
        content_size: str = "medium",
    ) -> WebSearchResponse:
        """通过智谱 AI web-search-pro 执行网页搜索

        Args:
            query: 搜索关键词或问题
            max_results: 最大返回结果数（1-50，API 上限 50）
            search_engine: 搜索引擎标识（默认 search_pro）
            search_domain_filter: 限定搜索域名（如 "www.example.com"），为 None 时不限制
            search_recency_filter: 时间范围过滤，可选 noLimit/day/week/month/year
            content_size: 摘要长度控制，可选 low/medium/high

        Returns:
            WebSearchResponse 包含搜索结果列表

        Raises:
            ParseError: API 响应解析失败时
        """
        try:
            count = max(1, min(int(max_results), 50))
        except (TypeError, ValueError):
            count = 10

        payload: dict[str, Any] = {
            "tool": "web-search-pro",
            "messages": [{"role": "user", "content": query}],
            "stream": False,
            "search_engine": search_engine,
            "count": count,
        }

        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter.strip()

        recency = search_recency_filter if search_recency_filter in _VALID_RECENCY else "noLimit"
        if recency != "noLimit":
            payload["search_recency_filter"] = recency

        size = content_size if content_size in _VALID_CONTENT_SIZES else "medium"
        payload["content_size"] = size

        resp = await self.post(
            "/api/paas/v4/tools",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"智谱 AI 搜索响应解析失败: {e}") from e

        results: list[WebSearchResult] = []

        # 从 choices[0].message.tool_calls[*].search_result 提取搜索结果
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            for tool_call in tool_calls:
                search_result = tool_call.get("search_result") or []
                for item in search_result:
                    title = (item.get("title") or "").strip()
                    url = (item.get("link") or "").strip()
                    if not title or not url:
                        continue
                    snippet = (item.get("content") or "").strip()
                    raw: dict[str, Any] = {}
                    if item.get("icon"):
                        raw["icon"] = item["icon"]
                    if item.get("media"):
                        raw["media"] = item["media"]
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_ZHIPUAI,
                            title=title,
                            url=url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                            raw=raw,
                        )
                    )

        logger.info("智谱 AI 搜索返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_ZHIPUAI,
            results=results,
            total_results=len(results),
        )
