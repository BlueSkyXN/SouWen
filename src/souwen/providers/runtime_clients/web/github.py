"""GitHub 搜索 API 客户端"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.providers.runtime_clients.web.github")


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
        self.token = (
            token if token is not None else config.resolve_api_key("github", "github_token")
        )

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
            from souwen.common_runtime.provider_support.exceptions import ParseError

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
                    source="github",
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
            source="github",
            results=results,
            total_results=len(results),
        )
