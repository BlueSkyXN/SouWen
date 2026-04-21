"""LinuxDo 论坛搜索客户端

文件用途：
    LinuxDo（linux.do）论坛搜索客户端。通过 Discourse 平台
    提供的公开 search.json API 检索论坛帖子，无需 API Key。
    返回结果统一映射为 SouWen 的 WebSearchResult 模型。

    LinuxDo 是基于 Discourse 构建的热门中文技术社区，
    其搜索 API 返回结构化的 topics + posts 数据。

函数/类清单：
    LinuxDoClient（类）
        - 功能：LinuxDo 论坛搜索客户端
        - 继承：SouWenHttpClient
        - 关键属性：ENGINE_NAME = "linuxdo",
                  BASE_URL = "https://linux.do"
        - 主要方法：search(query, max_results) -> WebSearchResponse

模块依赖：
    - logging: 日志记录
    - re: HTML 标签清理
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse
    - souwen.http_client: SouWenHttpClient
"""

from __future__ import annotations

import logging
import re

from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.linuxdo")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    """移除 HTML 标签（如搜索高亮 <span> 标记）"""
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


class LinuxDoClient(SouWenHttpClient):
    """LinuxDo 论坛搜索客户端

    基于 Discourse 平台的中文技术社区。
    使用 Discourse 公开 search.json API，无需 API Key。

    返回结果关联 posts（匹配的具体回帖）与 topics（主题标题），
    构建完整的帖子链接。
    """

    ENGINE_NAME = "linuxdo"
    BASE_URL = "https://linux.do"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 LinuxDo 论坛帖子

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 20）

        Returns:
            WebSearchResponse 包含搜索结果
        """
        results: list[WebSearchResult] = []

        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/search.json",
                params={"q": query},
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        except Exception as e:
            logger.warning("LinuxDo 搜索请求失败: %s", e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_LINUXDO,
                results=[],
                total_results=0,
            )

        # Discourse search.json 返回:
        # - topics: [{id, title, slug, category_id, like_count, posts_count, ...}]
        # - posts: [{id, topic_id, blurb, post_number, username, like_count, ...}]
        topics_list = data.get("topics", [])
        posts_list = data.get("posts", [])

        # 构建 topic_id -> topic 映射，便于 post 关联
        topic_map: dict[int, dict] = {}
        for topic in topics_list:
            tid = topic.get("id")
            if tid is not None:
                topic_map[tid] = topic

        # 优先遍历 posts（按相关性排序），关联到对应 topic 获取标题
        for post in posts_list:
            if len(results) >= max_results:
                break

            topic_id = post.get("topic_id")
            post_number = post.get("post_number", 1)
            blurb = _clean_html(post.get("blurb", ""))
            username = post.get("username", "")
            like_count = post.get("like_count", 0)

            # 从 topic_map 获取标题和 slug
            topic = topic_map.get(topic_id, {})
            title = topic.get("title") or topic.get("fancy_title", "")
            slug = topic.get("slug", "")

            if not title or not topic_id:
                continue

            # 构建帖子链接
            if slug:
                url = f"https://linux.do/t/{slug}/{topic_id}/{post_number}"
            else:
                url = f"https://linux.do/t/{topic_id}/{post_number}"

            # 构建 snippet
            parts = [blurb]
            if username:
                parts.append(f"@{username}")
            if like_count:
                parts.append(f"👍{like_count}")

            snippet = " | ".join(p for p in parts if p)

            results.append(
                WebSearchResult(
                    source=SourceType.WEB_LINUXDO,
                    title=_clean_html(title),
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                )
            )

        # 如果 posts 不够，补充 topics（仅标题匹配）
        if len(results) < max_results:
            seen_topic_ids = {post.get("topic_id") for post in posts_list}
            for topic in topics_list:
                if len(results) >= max_results:
                    break

                tid = topic.get("id")
                if tid in seen_topic_ids:
                    continue

                title = topic.get("title") or topic.get("fancy_title", "")
                slug = topic.get("slug", "")

                if not title or not tid:
                    continue

                if slug:
                    url = f"https://linux.do/t/{slug}/{tid}"
                else:
                    url = f"https://linux.do/t/{tid}"

                posts_count = topic.get("posts_count", 0)
                like_count = topic.get("like_count", 0)

                parts = []
                if posts_count:
                    parts.append(f"回复: {posts_count}")
                if like_count:
                    parts.append(f"👍{like_count}")

                snippet = " | ".join(p for p in parts if p)

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_LINUXDO,
                        title=_clean_html(title),
                        url=url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

        logger.info("LinuxDo 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_LINUXDO,
            results=results,
            total_results=len(results),
        )
