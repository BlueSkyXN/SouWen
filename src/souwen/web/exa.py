"""Exa 语义搜索 API 客户端

文件用途：
    Exa 语义搜索客户端。Exa 使用自建神经索引进行语义搜索（非关键词匹配），
    适合查找相似内容、人物、公司、代码等。支持相似链接搜索。

函数/类清单：
    ExaClient（类）
        - 功能：Exa 语义搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "exa", BASE_URL = "https://api.exa.ai",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(...) -> WebSearchResponse, find_similar(...) -> WebSearchResponse,
                  contents(...) -> FetchResponse

    ExaClient.__init__(api_key=None)
        - 功能：初始化 Exa 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_EXA_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ExaClient.search(query, max_results=10, search_type="auto", use_autoprompt=True,
                    include_text=True, include_domains=None, exclude_domains=None) -> WebSearchResponse
        - 功能：通过 Exa API 执行语义搜索
        - 输入：query 搜索词（支持自然语言）, max_results 最大结果数, search_type 搜索类型,
                use_autoprompt 是否让 Exa 优化查询, include_text 是否提取页面文本,
                include_domains 限定域名, exclude_domains 排除域名
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

    ExaClient.find_similar(url, max_results=10) -> WebSearchResponse
        - 功能：查找与给定 URL 相似的页面
        - 输入：url 目标 URL, max_results 最大返回结果数
        - 输出：WebSearchResponse 相似页面结果
        - 异常：ParseError API 响应解析失败时抛出

    ExaClient.contents(urls, timeout=30.0) -> FetchResponse
        - 功能：通过 Exa Contents API 批量获取 URL 内容（原生支持批量）
        - 输入：urls 目标 URL 列表, timeout 超时秒数
        - 输出：FetchResponse 包含提取结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：/search（语义搜索）、/findSimilar（相似链接搜索）、/contents（内容提取）
    - 请求头 x-api-key 用于身份认证
    - 支持搜索类型：auto（自动）、neural（神经）、keyword（关键词）
    - Snippet 最长 500 字符
    - 收集元数据：relevance_score（相关性）、published_date（发布日期）、author（作者）
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse, FetchResult, FetchResponse

logger = logging.getLogger("souwen.web.exa")


class ExaClient(SouWenHttpClient):
    """Exa 语义搜索客户端

    Args:
        api_key: Exa API Key，默认从 SOUWEN_EXA_API_KEY 读取
    """

    ENGINE_NAME = "exa"
    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("exa", "exa_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "exa_api_key",
                "Exa",
                "https://dashboard.exa.ai/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="exa")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_type: str = "auto",
        use_autoprompt: bool = True,
        include_text: bool = True,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> WebSearchResponse:
        """通过 Exa API 语义搜索

        Args:
            query: 搜索关键词（支持自然语言描述）
            max_results: 最大返回结果数
            search_type: 搜索类型 "auto" / "neural" / "keyword"
            use_autoprompt: 是否让 Exa 优化查询
            include_text: 是否提取页面文本内容
            include_domains: 限定域名
            exclude_domains: 排除域名

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # 构建请求载荷
        payload: dict[str, Any] = {
            "query": query,
            "numResults": min(max_results, 100),  # API 最多返回 100 条
            "type": search_type,
            "useAutoprompt": use_autoprompt,
        }
        # 可选参数
        if include_text:
            payload["contents"] = {"text": True}  # 返回页面清洗后的文本
        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains

        # 发送 POST 请求到 Exa API
        resp = await self.post(
            "/search",
            json=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Exa 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 提取页面文本（最长 500 字符）
            snippet = item.get("text", "").strip()[:500] if item.get("text") else ""
            # 收集元数据
            raw: dict[str, Any] = {}
            if item.get("score"):
                raw["relevance_score"] = item["score"]  # 语义相关性分数
            if item.get("publishedDate"):
                raw["published_date"] = item["publishedDate"]  # 发布日期
            if item.get("author"):
                raw["author"] = item["author"]  # 作者
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_EXA,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Exa 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_EXA,
            results=results,
            total_results=len(results),
        )

    async def find_similar(
        self,
        url: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """查找与给定 URL 相似的页面

        根据目标 URL 的内容，使用神经网络查找语义相似的页面。
        这是一种补充搜索方式，适合探索相关话题。

        Args:
            url: 目标 URL
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 相似页面结果
        """
        # 构建请求载荷
        payload: dict[str, Any] = {
            "url": url,
            "numResults": min(max_results, 100),  # API 最多返回 100 条
            "contents": {"text": True},  # 返回页面清洗后的文本
        }

        # 发送 POST 请求到 findSimilar 端点
        resp = await self.post(
            "/findSimilar",
            json=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Exa find_similar 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取相似页面结果
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            result_url = item.get("url", "").strip()
            if not title or not result_url:
                # 跳过不完整的结果
                continue
            # 提取页面文本（最长 500 字符）
            snippet = item.get("text", "").strip()[:500] if item.get("text") else ""
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_EXA,
                    title=title,
                    url=result_url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw={"score": item.get("score")},  # 相似度分数
                )
            )

        # 返回相似页面搜索的响应
        return WebSearchResponse(
            query=f"similar:{url}",  # 标记为相似查询
            source=SourceType.WEB_EXA,
            results=results,
            total_results=len(results),
        )

    async def contents(self, urls: list[str], timeout: float = 30.0) -> FetchResponse:
        """通过 Exa Contents API 批量获取 URL 内容

        Exa 的 /contents 端点原生支持批量 URL 处理。

        Args:
            urls: 目标 URL 列表
            timeout: 超时秒数

        Returns:
            FetchResponse 包含提取结果
        """
        payload: dict[str, Any] = {
            "urls": urls,
            "text": True,
        }
        try:
            resp = await self.post(
                "/contents",
                json=payload,
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
            )
            try:
                data = resp.json()
            except Exception as e:
                from souwen.exceptions import ParseError

                raise ParseError(f"Exa Contents 响应解析失败: {e}") from e

            results: list[FetchResult] = []
            url_set = set(urls)
            seen_urls: set[str] = set()
            for item in data.get("results", []):
                result_url = item.get("url", "")
                seen_urls.add(result_url)
                text = item.get("text", "")
                results.append(
                    FetchResult(
                        url=result_url,
                        final_url=result_url,
                        title=item.get("title", ""),
                        content=text,
                        content_format="text",
                        source="exa",
                        snippet=text[:500] if text else "",
                        published_date=item.get("publishedDate"),
                        author=item.get("author"),
                        raw={"provider": "exa_contents", "id": item.get("id")},
                    )
                )
            # 标记未在响应中出现的 URL 为失败
            for missing_url in url_set - seen_urls:
                results.append(
                    FetchResult(
                        url=missing_url,
                        final_url=missing_url,
                        source="exa",
                        error="URL not found in Exa contents response",
                        raw={"provider": "exa_contents"},
                    )
                )

            ok = sum(1 for r in results if r.error is None)
            return FetchResponse(
                urls=urls,
                results=results,
                total=len(results),
                total_ok=ok,
                total_failed=len(results) - ok,
                provider="exa",
            )
        except Exception as exc:
            logger.warning("Exa contents failed: urls=%s err=%s", urls, exc)
            results = [
                FetchResult(
                    url=u,
                    final_url=u,
                    source="exa",
                    error=str(exc),
                    raw={"provider": "exa_contents"},
                )
                for u in urls
            ]
            return FetchResponse(
                urls=urls,
                results=results,
                total=len(results),
                total_ok=0,
                total_failed=len(results),
                provider="exa",
            )
