"""GitHub 搜索 API 客户端

文件用途：
    GitHub REST API v3 搜索客户端。封装 GitHub 官方搜索接口，目前实现仓库搜索
    （/search/repositories），将仓库元数据归一化为统一 ``WebSearchResult`` 模型。
    无需 API Token 即可使用（未认证免费额度 10 req/min），提供 Token 后可提升至
    30 req/min；与其他需要付费 Key 的搜索引擎不同，未配置 Token 时降级运行而非抛错。

函数/类清单：
    GitHubClient（类）
        - 功能：GitHub REST API 搜索客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "github", BASE_URL = "https://api.github.com",
                  token (str|None) 可选的 Personal Access Token
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse

    GitHubClient.__init__(token=None)
        - 功能：初始化 GitHub 搜索客户端，自动设置鉴权头
        - 输入：token (str|None) Personal Access Token，
                默认从 SOUWEN_GITHUB_TOKEN / config.github_token 读取
        - 输出：实例（无 Token 时使用未认证模式，不抛异常）

    GitHubClient.search(query, max_results=10, sort="stars", order="desc") -> WebSearchResponse
        - 功能：通过 GitHub Search API 搜索仓库
        - 输入：query 搜索词（支持 GitHub 搜索语法，如 "language:python stars:>1000"）,
                max_results 最大结果数（API 单页上限 100）,
                sort 排序字段（stars/forks/help-wanted-issues/updated）,
                order 排序方向（desc/asc）
        - 输出：WebSearchResponse 包含 WebSearchResult 列表
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET /search/repositories?q=...&sort=...&order=...&per_page=...
    - 鉴权：Bearer Token（Personal Access Token），可选；未配置走匿名免费额度
    - 请求头：Accept: application/vnd.github+json（推荐使用 v3 媒体类型）
    - 单次返回上限 100；如需更多需翻页（当前实现只返回首页）
    - 限流：未认证 10 req/min，认证 30 req/min（搜索接口独立配额）
    - 文档：https://docs.github.com/en/rest/search/search
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.github")


class GitHubClient(SouWenHttpClient):
    """GitHub REST API 搜索客户端

    Args:
        token: GitHub Personal Access Token，默认从 SOUWEN_GITHUB_TOKEN /
               配置 ``github_token`` 读取；为空则使用未认证免费额度（10 req/min）
    """

    ENGINE_NAME = "github"
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        # 从参数或配置读取 Token，未提供也允许（降级为未认证免费额度）
        config = get_config()
        self.token = token or config.resolve_api_key("github", "github_token")

        # GitHub 推荐使用 v3 媒体类型并显式带 X-GitHub-Api-Version
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            # 提供 Token 时附带 Bearer 鉴权头
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.debug("GitHub 未配置 Token，使用未认证模式（10 req/min）")

        super().__init__(
            base_url=self.BASE_URL,
            headers=headers,
            source_name="github",
        )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "stars",
        order: str = "desc",
    ) -> WebSearchResponse:
        """通过 GitHub Search API 搜索仓库

        Args:
            query: 搜索关键词，支持 GitHub 搜索语法
                  （如 ``"machine learning language:python stars:>1000"``）
            max_results: 最大返回结果数（API 单页上限 100）
            sort: 排序字段，可选 ``stars`` / ``forks`` / ``help-wanted-issues`` / ``updated``
            order: 排序方向，``desc`` 或 ``asc``
        """
        # GitHub Search API 单页上限 100，超出需要翻页（这里只取首页）
        per_page = min(max_results, 100)
        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
        }

        resp = await self.get("/search/repositories", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"GitHub 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("items", []):
            if len(results) >= max_results:
                break
            # 仓库标题使用 owner/repo 全名，URL 使用 html_url（用户访问页）
            full_name = (item.get("full_name") or "").strip()
            html_url = (item.get("html_url") or "").strip()
            if not full_name or not html_url:
                continue

            # 收集对排序/筛选有用的元数据，避免直接塞整个 item 增大体积
            raw: dict[str, Any] = {
                "stars": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "language": item.get("language"),
                "updated_at": item.get("updated_at"),
                "topics": item.get("topics") or [],
                "open_issues": item.get("open_issues_count"),
                "license": (item.get("license") or {}).get("spdx_id"),
                "owner": (item.get("owner") or {}).get("login"),
                "archived": item.get("archived", False),
            }

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_GITHUB,
                    title=full_name,
                    url=html_url,
                    snippet=(item.get("description") or "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        total_count = data.get("total_count", len(results))
        logger.info("GitHub 返回 %d 条结果 (query=%s, total=%s)", len(results), query, total_count)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_GITHUB,
            results=results,
            total_results=len(results),
        )
