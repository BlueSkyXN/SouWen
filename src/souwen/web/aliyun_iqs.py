"""阿里云 IQS（Intelligent Query Service）搜索客户端

文件用途：
    阿里云 IQS 搜索客户端。IQS 是阿里云提供的智能查询服务，通过大模型优化与
    多数据源融合，提供实时、高质量的搜索结果。本模块参考
    @tongxiao/common-search-mcp-server 的实现逻辑，用 Python 重现其核心功能。

    原始实现（Node.js）：https://www.npmjs.com/package/@tongxiao/common-search-mcp-server
    API 文档：https://help.aliyun.com/product/2837261.html

函数/类清单：
    AliyunIQSClient（类）
        - 功能：阿里云 IQS 搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "aliyun_iqs", BASE_URL = "https://cloud-iqs.aliyuncs.com",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results) -> WebSearchResponse

    AliyunIQSClient.__init__(api_key=None)
        - 功能：初始化阿里云 IQS 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_ALIYUN_IQS_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    AliyunIQSClient.search(query, max_results=5) -> WebSearchResponse
        - 功能：通过阿里云 IQS API 执行搜索
        - 输入：query 搜索词, max_results 最大结果数（默认 5，与原始实现一致）
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：POST /search/llm，api_key 通过 X-API-Key 请求头传递
    - 请求体：{"query": "...", "numResults": N}
    - 响应字段：pageItems[].{title, link, hostname, publishTime, summary, snippet}
    - publishTime 为毫秒时间戳，转换为 ISO 日期字符串
    - summary 优先于 snippet 作为摘要内容
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.aliyun_iqs")


class AliyunIQSClient(SouWenHttpClient):
    """阿里云 IQS（Intelligent Query Service）搜索客户端

    参考 @tongxiao/common-search-mcp-server 的原始实现，用 Python 重现
    阿里云 IQS 搜索功能。IQS 通过大模型优化与多数据源融合提供高质量搜索结果。

    Args:
        api_key: 阿里云 IQS API Key，默认从 SOUWEN_ALIYUN_IQS_API_KEY 读取。
                 可从 https://ipaas.console.aliyun.com/api-key 获取。
    """

    ENGINE_NAME = "aliyun_iqs"
    BASE_URL = "https://cloud-iqs.aliyuncs.com"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("aliyun_iqs", "aliyun_iqs_api_key")
        if not self.api_key:
            raise ConfigError(
                "aliyun_iqs_api_key",
                "阿里云 IQS",
                "https://ipaas.console.aliyun.com/api-key",
            )
        super().__init__(base_url=self.BASE_URL, source_name="aliyun_iqs")

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> WebSearchResponse:
        """通过阿里云 IQS API 搜索

        Args:
            query: 搜索关键词（长度 2~100 个字符）
            max_results: 最大返回结果数（原始实现默认为 5）
        """
        payload: dict[str, Any] = {
            "query": query,
            "numResults": max(1, max_results),
        }

        # X-API-Key 放在请求头，与原始 Node.js 实现一致
        resp = await self.post(
            "/search/llm",
            json=payload,
            headers={"X-API-Key": self.api_key},
        )

        try:
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"阿里云 IQS 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("pageItems", []):
            title = (item.get("title") or "").strip()
            url = (item.get("link") or "").strip()
            if not title or not url:
                continue

            # 优先使用 summary，回退到 snippet（与原始实现一致）
            snippet = (item.get("summary") or item.get("snippet") or "").strip()

            # publishTime 为毫秒时间戳，转为 YYYY-MM-DD 格式
            pub_date: str | None = None
            publish_time = item.get("publishTime")
            if publish_time:
                try:
                    from datetime import datetime, timezone

                    pub_date = datetime.fromtimestamp(
                        int(publish_time) / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    pass

            raw: dict[str, Any] = {}
            hostname = item.get("hostname")
            if hostname:
                raw["hostname"] = hostname
            if pub_date:
                raw["publish_date"] = pub_date

            results.append(
                WebSearchResult(
                    source="aliyun_iqs",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("阿里云 IQS 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="aliyun_iqs",
            results=results,
            total_results=len(results),
        )
