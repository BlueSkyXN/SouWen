"""DuckDuckGo JSON 搜索基类

为 News/Images/Videos 提供共享的 VQD token 管理和 JSON 分页逻辑。
所有 JSON 端点（i.js, news.js, v.js）共用同一模式：
    1. 从首页获取 VQD token
    2. GET 请求 JSON 端点，附带 VQD + 过滤参数
    3. 通过响应中的 next URL 解析 s= 偏移实现分页
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.core.scraper.base import BaseScraper
from souwen.web.ddg_utils import extract_vqd, parse_next_offset

logger = logging.getLogger("souwen.web.ddg_json")


class DDGJsonClient(BaseScraper):
    """DDG JSON 端点搜索基类

    子类需设置:
        ENGINE_NAME: str
        BASE_URL: str = "https://duckduckgo.com"
        _ENDPOINT: str (如 "/i.js", "/news.js", "/v.js")
        _MAX_PAGES: int = 5
    """

    BASE_URL = "https://duckduckgo.com"
    _ENDPOINT: str = ""
    _MAX_PAGES: int = 5

    def __init__(self, **kwargs):
        super().__init__(
            min_delay=0.75,
            max_delay=1.5,
            max_retries=3,
            follow_redirects=False,
            **kwargs,
        )

    async def _get_vqd(self, keywords: str) -> str | None:
        """从 DuckDuckGo 首页获取 VQD token（per-query）"""
        try:
            resp = await self._fetch(
                "https://duckduckgo.com",
                params={"q": keywords},
                headers={"Referer": "https://duckduckgo.com/"},
            )
            if resp.status_code != 200:
                logger.warning("VQD 获取失败: status=%d", resp.status_code)
                return None
            content = resp.content if hasattr(resp, "content") else resp.text.encode()
            return extract_vqd(content, keywords)
        except Exception as e:
            logger.warning("VQD 获取异常: %s", e)
            return None

    async def _fetch_json_page(self, params: dict[str, str]) -> dict[str, Any] | None:
        """请求 JSON 端点并返回解析后的字典"""
        url = f"{self._resolved_base_url}{self._ENDPOINT}"
        try:
            resp = await self._fetch(
                url,
                params=params,
                headers={"Referer": "https://duckduckgo.com/"},
            )
            if resp.status_code in (301, 302, 202, 403, 418, 429):
                logger.warning("DDG JSON 反爬 status=%d", resp.status_code)
                return None
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception as e:
            logger.warning("DDG JSON 请求失败: %s", e)
            return None

    async def _paginated_search(
        self,
        keywords: str,
        base_params: dict[str, str],
        max_results: int,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """通用分页搜索循环

        Args:
            keywords: 搜索关键词
            base_params: 基础请求参数（包含 vqd, q, l, o, p 等）
            max_results: 最大结果数
            max_pages: 最大页数

        Returns:
            原始结果字典列表
        """
        pages = max_pages or self._MAX_PAGES
        all_results: list[dict[str, Any]] = []
        params = dict(base_params)

        for page in range(pages):
            data = await self._fetch_json_page(params)
            if data is None:
                break

            results = data.get("results")
            if not results:
                break

            all_results.extend(results)
            if len(all_results) >= max_results:
                break

            # 解析分页偏移
            next_url = data.get("next")
            offset = parse_next_offset(next_url)
            if not offset:
                break
            params["s"] = offset

        return all_results[:max_results]
