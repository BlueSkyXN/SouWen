"""Whoogle 自部署隐私搜索代理

文件用途：
    Whoogle 搜索客户端。Whoogle 是 Google 搜索的自部署隐私代理镜像，
    无追踪、无广告、无 JavaScript，需用户自行部署实例。

函数/类清单：
    WhoogleClient（类）
        - 功能：通过 HTML 解析获取 Whoogle（Google 代理）搜索结果
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "whoogle", instance_url 自部署实例地址
        - 主要方法：search(query, max_results) -> WebSearchResponse

    WhoogleClient.__init__(instance_url=None)
        - 功能：初始化 Whoogle 搜索客户端，验证实例 URL 可用性
        - 输入：instance_url (str|None) 实例地址，默认从 SOUWEN_WHOOGLE_URL 读取
        - 异常：ConfigError 未提供实例 URL 时抛出

    WhoogleClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：通过 Whoogle 实例搜索，HTML 解析提取结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取实例 URL 配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - Whoogle 是 Google 搜索的隐私代理，返回 Google SERP 页面
    - 使用 BeautifulSoup 解析 HTML，CSS 选择器提取结果
    - 支持两套选择器降级（div.ZINbbc / div.g）
    - 需要用户自部署 Whoogle 实例并提供 URL
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.whoogle")


class WhoogleClient(SouWenHttpClient):
    """Whoogle HTML 搜索客户端

    Args:
        instance_url: Whoogle 实例 URL (如 http://localhost:5000)
                     默认从 SOUWEN_WHOOGLE_URL 环境变量读取
    """

    ENGINE_NAME = "whoogle"

    def __init__(self, instance_url: str | None = None):
        # 从参数或配置读取 Whoogle 实例 URL
        config = get_config()
        self.instance_url = (
            instance_url or config.resolve_api_key("whoogle", "whoogle_url") or ""
        ).rstrip("/")
        if not self.instance_url:
            # 未提供实例 URL 时抛出配置错误
            raise ConfigError(
                "whoogle_url",
                "Whoogle",
                "https://github.com/benbusby/whoogle-search",
            )
        super().__init__(base_url=self.instance_url, source_name="whoogle")

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> WebSearchResponse:
        """通过 Whoogle 搜索（HTML 解析）

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        # 构建搜索查询参数
        params: dict[str, Any] = {"q": query}

        # 发送 GET 请求到 Whoogle 实例
        resp = await self.get("/search", params=params)
        try:
            from bs4 import BeautifulSoup

            # 使用 BeautifulSoup 解析返回的 HTML 页面
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Whoogle HTML 解析失败: {e}") from e

        results: list[WebSearchResult] = []
        try:
            # 尝试两套 CSS 选择器定位结果容器（降级策略）
            containers = soup.select("div.ZINbbc") or soup.select("div.g")
            for container in containers:
                if len(results) >= max_results:
                    break

                # 提取标题
                title_tag = container.select_one("h3")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not title:
                    continue

                # 提取 URL
                link_tag = container.select_one("a")
                if not link_tag:
                    continue
                url = link_tag.get("href", "")
                if isinstance(url, list):
                    # href 可能返回列表类型，取第一个
                    url = url[0] if url else ""
                url = str(url).strip()
                if not url.startswith("http"):
                    continue

                # 提取摘要
                snippet = ""
                # 尝试精确选择器提取摘要，失败则降级到通用 BNeawe 类
                snippet_tag = container.select_one(".BNeawe.s3v9rd")
                if not snippet_tag:
                    for tag in container.select("div.BNeawe"):
                        if tag != title_tag and "h3" not in [c.name for c in tag.parents]:
                            snippet = tag.get_text(strip=True)
                            break
                else:
                    snippet = snippet_tag.get_text(strip=True)

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_WHOOGLE,
                        title=title,
                        url=url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Whoogle 结果提取失败: {e}") from e

        logger.info("Whoogle 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_WHOOGLE,
            results=results,
            total_results=len(results),
        )
