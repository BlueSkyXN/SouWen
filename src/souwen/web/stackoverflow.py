"""StackOverflow（StackExchange）搜索 API 客户端

文件用途：
    StackExchange API v2.3 搜索客户端。封装 /search/advanced 端点，对 StackOverflow
    站点的问答内容做关键词检索。无 API Key 时按 IP 限额（约 300 次/天）正常工作，
    配置 API Key 后配额提升至约 10000 次/天。响应默认为 gzip 压缩，httpx 会自动解压。

函数/类清单：
    StackOverflowClient（类）
        - 功能：StackExchange API 搜索客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "stackoverflow",
                  BASE_URL = "https://api.stackexchange.com/2.3",
                  api_key (str|None) 可选 API 密钥
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse

    StackOverflowClient.__init__(api_key=None)
        - 功能：初始化 StackOverflow 搜索客户端，API Key 可选
        - 输入：api_key (str|None) 可选 API 密钥，默认从配置 stackoverflow_api_key 读取
        - 异常：不抛出 ConfigError，缺失 API Key 时仍可工作（采用匿名配额）

    StackOverflowClient.search(query, max_results=10, site="stackoverflow", ...) -> WebSearchResponse
        - 功能：通过 StackExchange API 搜索指定站点（默认 stackoverflow）的问答
        - 输入：query 搜索词, max_results 最大结果数（API 上限 100），
                site 站点参数（默认 "stackoverflow"），
                sort 排序方式（默认 "relevance"），order 排序方向（默认 "desc"）
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - html: HTML 实体解码（StackExchange 返回 HTML 编码标题）
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET /search/advanced，参数 q/site/pagesize/sort/order/filter
    - 响应默认 gzip 压缩，httpx 自动解压（无需特殊处理）
    - title 字段为 HTML 编码（如 &amp; / &#39;），需 html.unescape() 还原
    - 默认 filter 已包含 score / answer_count / tags / view_count / is_answered 等元数据
    - quota_remaining / has_more 字段写入响应 raw 中，便于上层观测剩余配额
    - 无 API Key 时仍可使用，仅按 IP 享受较低的匿名配额（约 300 次/天）
"""

from __future__ import annotations

import html
import logging
from typing import Any

from souwen.config import get_config
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.stackoverflow")


class StackOverflowClient(SouWenHttpClient):
    """StackOverflow（StackExchange）搜索客户端

    Args:
        api_key: StackExchange API Key，可选；
                 默认从 SOUWEN_STACKOVERFLOW_API_KEY 读取，
                 缺失时按匿名 IP 配额工作（约 300 次/天）
    """

    ENGINE_NAME = "stackoverflow"
    BASE_URL = "https://api.stackexchange.com/2.3"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key（可选）
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("stackoverflow", "stackoverflow_api_key")
        # 注意：StackExchange API 允许匿名调用，无 Key 时不抛 ConfigError
        super().__init__(base_url=self.BASE_URL, source_name="stackoverflow")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        site: str = "stackoverflow",
        sort: str = "relevance",
        order: str = "desc",
    ) -> WebSearchResponse:
        """通过 StackExchange API 搜索 StackOverflow 问答

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (API 上限 100)
            site: StackExchange 站点标识 (默认 "stackoverflow")
            sort: 排序字段 "relevance"/"votes"/"creation"/"activity"
            order: 排序方向 "desc" 或 "asc"
        """
        # 构建查询参数
        params: dict[str, Any] = {
            "q": query,
            "site": site,
            "pagesize": min(max_results, 100),  # API 单页上限 100
            "sort": sort,
            "order": order,
            "filter": "default",
        }
        # 有 Key 则附带，享受高配额（10000/天）
        if self.api_key:
            params["key"] = self.api_key

        # 发送 GET 请求；响应为 gzip，httpx 自动解压
        resp = await self.get("/search/advanced", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"StackOverflow 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 解析 items 数组
        for item in data.get("items", []):
            if len(results) >= max_results:
                break
            # title 是 HTML 编码的（如 &amp; / &#39;），需还原
            title = html.unescape((item.get("title") or "").strip())
            url = (item.get("link") or "").strip()
            if not title or not url:
                # 跳过缺失关键字段的条目
                continue
            # 由 tags / score / answer_count 拼装可读 snippet
            tags = item.get("tags") or []
            score = item.get("score", 0)
            answer_count = item.get("answer_count", 0)
            is_answered = item.get("is_answered", False)
            answered_mark = "✓" if is_answered else "·"
            tags_part = f"[{', '.join(tags)}] " if tags else ""
            snippet = f"{tags_part}score={score}, answers={answer_count} {answered_mark}"
            # 完整元数据放入 raw
            raw: dict[str, Any] = {
                "question_id": item.get("question_id"),
                "score": score,
                "answer_count": answer_count,
                "tags": tags,
                "view_count": item.get("view_count"),
                "is_answered": is_answered,
                "creation_date": item.get("creation_date"),
                "last_activity_date": item.get("last_activity_date"),
                "accepted_answer_id": item.get("accepted_answer_id"),
            }
            # 过滤掉值为 None 的字段，保持 raw 紧凑
            raw = {k: v for k, v in raw.items() if v is not None}
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_STACKOVERFLOW,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # 记录配额信息（便于诊断 429）
        quota_remaining = data.get("quota_remaining")
        has_more = data.get("has_more")
        if quota_remaining is not None:
            logger.debug(
                "StackOverflow quota_remaining=%s has_more=%s",
                quota_remaining,
                has_more,
            )

        logger.info("StackOverflow 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_STACKOVERFLOW,
            results=results,
            total_results=len(results),
        )
