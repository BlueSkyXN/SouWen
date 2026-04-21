"""Bilibili 精简客户端（搜索 + 抓取）

文件用途：
    B 站（bilibili.com）Web API 的 Python 客户端，聚焦 SouWen 的核心使命
    "搜索 + 抓取"：

        - 视频搜索（WBI 签名，参与聚合搜索）
        - 用户搜索
        - 专栏文章搜索
        - 视频详情抓取（按 BV 号）

    其他派生功能（评论 / 字幕 / AI 摘要 / 热门 / 排行 / 相关推荐 / 用户信息 /
    用户视频列表）属于独立的 bili-cli 项目范畴，本仓库不再提供。

    继承 BaseScraper 复用 TLS 指纹模拟、浏览器请求头、自适应限速与自动重试，
    降低被风控的概率。

设计约定：
    - 聚合方法（search / search_users / search_articles）：
      失败降级为空结果，不抛异常，便于参与多源聚合。
    - 查找方法（get_video_details）：
      失败抛 _errors.py 中定义的强类型异常，由调用方决定如何处理。

模块依赖：
    - urllib.parse：URL 编码
    - souwen.models：SourceType / WebSearchResponse / WebSearchResult
    - souwen.scraper.base：BaseScraper
    - souwen.config：可选 SESSDATA / bili_jct 读取
    - souwen.web.bilibili.wbi：WBI 签名器
    - souwen.web.bilibili.models：B 站详情数据模型
    - souwen.web.bilibili._errors：错误码 → 异常映射

技术要点：
    - 所有请求必须带 Referer/Origin = https://www.bilibili.com，
      否则 -412 风控；同时附带匿名 buvid3 / buvid4 Cookie 提升通过率。
    - WBI 签名失败时（-403 / -352），自动失效缓存并重试一次。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

from souwen.config import get_config
from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.scraper.base import BaseScraper
from souwen.web.bilibili._errors import raise_for_code
from souwen.web.bilibili.models import (
    BilibiliArticleResult,
    BilibiliSearchUserItem,
    BilibiliVideoDetail,
    VideoOwner,
    VideoStat,
)
from souwen.web.bilibili.wbi import WbiSigner

logger = logging.getLogger("souwen.web.bilibili")


# 匿名 buvid Cookie — 部分接口在无登录态下也要求 cookie 中带 buvid，
# 缺失会被风控（-352）。这里使用全零占位，能通过大多数公开接口的校验。
_ANON_BUVID_COOKIE = (
    "buvid3=00000000-0000-0000-0000-000000000000infoc; "
    "buvid4=00000000-0000-0000-0000-000000000000-000000000000-000000000000"
)


class BilibiliClient(BaseScraper):
    """B 站全功能 Web API 客户端

    继承 BaseScraper 复用 TLS 指纹 + 自适应限速 + 自动重试。

    Attributes:
        ENGINE_NAME: 引擎标识 "bilibili"，用于配置解析
        BASE_URL:    API 基础地址 https://api.bilibili.com
    """

    ENGINE_NAME = "bilibili"
    BASE_URL = "https://api.bilibili.com"

    # 搜索单页上限（B 站接口硬限制）
    _MAX_PAGE_SIZE = 50
    # 搜索结果 snippet 截断长度
    _SNIPPET_MAX_LEN = 300
    # WBI -403/-352 触发的强制刷新错误码
    _WBI_INVALIDATE_CODES = (-403, -352)

    def __init__(self, **kwargs: Any) -> None:
        # 礼貌延迟 1~3 秒、重试 3 次；其余参数透传 BaseScraper
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)
        self._wbi = WbiSigner()

        # 可选 SESSDATA 登录态（提升风控通过率、可访问部分需要登录的接口）
        cfg = get_config()
        self._sessdata: str | None = getattr(cfg, "bilibili_sessdata", None)
        self._bili_jct: str | None = getattr(cfg, "bilibili_bili_jct", None)

    # ── 基础工具 ────────────────────────────────────────────

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """组装 B 站接口通用请求头

        Bilibili 对 Referer / Origin 强校验，缺失会触发 -412 风控。
        Cookie 中至少需要匿名 buvid，登录态可携带 SESSDATA。

        Args:
            extra: 额外覆盖的请求头

        Returns:
            合并后的请求头字典
        """
        headers: dict[str, str] = {
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

        cookie_parts: list[str] = [_ANON_BUVID_COOKIE]
        if self._sessdata:
            cookie_parts.append(f"SESSDATA={self._sessdata}")
        if self._bili_jct:
            cookie_parts.append(f"bili_jct={self._bili_jct}")
        headers["Cookie"] = "; ".join(cookie_parts)

        if extra:
            headers.update(extra)
        return headers

    async def _wbi_sign(self, params: dict[str, Any]) -> dict[str, str]:
        """对参数进行 WBI 签名（基于 self._fetch 拉取 nav 接口）"""

        async def _signer_fetch(url: str, headers: dict[str, str] | None = None):
            # 注意 nav 接口本身不应再嵌套 buvid Cookie 也无妨，复用 _build_headers
            merged = self._build_headers(headers or {})
            return await self._fetch(url, headers=merged)

        return await self._wbi.sign(_signer_fetch, params)

    @staticmethod
    def _parse_json(resp: Any) -> dict[str, Any]:
        """安全 JSON 解析"""
        try:
            payload = resp.json()
        except Exception as e:
            raise ValueError(f"响应不是合法 JSON: {e}") from e
        if not isinstance(payload, dict):
            raise ValueError(f"响应顶层不是 JSON 对象: {type(payload).__name__}")
        return payload

    @staticmethod
    def _check_code(payload: dict[str, Any]) -> dict[str, Any]:
        """检查 Bilibili 响应 code 字段，非 0 抛异常，0 返回 data 字段"""
        code = payload.get("code", 0)
        if code != 0:
            raise_for_code(int(code), str(payload.get("message", "")))
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def _wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        retry_on_risk: bool = True,
    ) -> dict[str, Any]:
        """执行 WBI 签名 GET 请求；遇 -403/-352 自动刷新 WBI key 并重试一次

        Args:
            path: 接口路径（以 / 开头）
            params: 原始查询参数（未签名）
            retry_on_risk: 是否在风控 code 时强制刷新 WBI 重试

        Returns:
            完整 JSON payload（含 code/message/data）
        """
        signed = await self._wbi_sign(params)
        url = f"{self.BASE_URL}{path}?{urlencode(signed)}"
        resp = await self._fetch(url, headers=self._build_headers())
        payload = self._parse_json(resp)

        code = payload.get("code", 0)
        if retry_on_risk and code in self._WBI_INVALIDATE_CODES:
            logger.warning("WBI 请求被风控 (code=%s)，刷新 key 重试一次", code)
            self._wbi.invalidate()
            signed = await self._wbi_sign(params)
            url = f"{self.BASE_URL}{path}?{urlencode(signed)}"
            resp = await self._fetch(url, headers=self._build_headers())
            payload = self._parse_json(resp)

        return payload

    async def _plain_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行普通 GET 请求（不带 WBI 签名）"""
        url = f"{self.BASE_URL}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        resp = await self._fetch(url, headers=self._build_headers())
        return self._parse_json(resp)

    @staticmethod
    def _clean_html(text: str) -> str:
        """清除 HTML 标签 — B 站搜索结果 title 含 <em class="keyword"> 高亮"""
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    # ── 视频搜索（聚合，不抛异常，向后兼容） ───────────────

    async def search(
        self,
        query: str,
        max_results: int = 20,
        order: str = "totalrank",
    ) -> WebSearchResponse:
        """搜索 B 站视频（WBI 签名）

        与旧版 BilibiliClient.search 保持完全相同的入参/返回结构，
        以满足 souwen.web.search 聚合调用的向后兼容性。

        Args:
            query: 搜索关键词
            max_results: 最大返回条数（B 站单页上限 50）
            order: 排序方式 — totalrank/click/pubdate/dm/stow

        Returns:
            WebSearchResponse — 失败时返回空结果而非抛异常
        """
        page_size = max(1, min(int(max_results), self._MAX_PAGE_SIZE))
        results: list[WebSearchResult] = []
        total_int = 0

        try:
            params: dict[str, Any] = {
                "search_type": "video",
                "keyword": query,
                "page": 1,
                "page_size": page_size,
                "order": order,
            }
            payload = await self._wbi_get("/x/web-interface/search/type", params)

            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 搜索返回错误 code=%s message=%s (query=%s)",
                    code,
                    payload.get("message"),
                    query,
                )
            else:
                data = payload.get("data") or {}
                items = data.get("result") or []
                if not isinstance(items, list):
                    items = []

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        title = self._clean_html(item.get("title", ""))
                        arcurl = item.get("arcurl") or ""
                        if not title or not arcurl:
                            continue
                        snippet = (item.get("description") or "")[: self._SNIPPET_MAX_LEN]
                        # 修正 // 协议相对 URL
                        if arcurl.startswith("//"):
                            arcurl = "https:" + arcurl
                        results.append(
                            WebSearchResult(
                                source=SourceType.WEB_BILIBILI,
                                title=title,
                                url=str(arcurl),
                                snippet=snippet,
                                engine=self.ENGINE_NAME,
                                raw={
                                    "author": item.get("author"),
                                    "mid": item.get("mid"),
                                    "play": item.get("play"),
                                    "video_review": item.get("video_review"),
                                    "favorites": item.get("favorites"),
                                    "duration": item.get("duration"),
                                    "pubdate": item.get("pubdate"),
                                    "tag": item.get("tag"),
                                    "bvid": item.get("bvid"),
                                    "aid": item.get("aid"),
                                },
                            )
                        )
                        if len(results) >= max_results:
                            break
                    except Exception as e:
                        logger.debug("Bilibili 单条结果解析失败: %s", e)
                        continue

                total = data.get("numResults")
                try:
                    total_int = int(total) if total is not None else len(results)
                except (TypeError, ValueError):
                    total_int = len(results)
        except Exception as e:
            logger.warning("Bilibili 搜索失败 (query=%s): %s", query, e)

        logger.info("Bilibili 搜索返回 %d 条 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BILIBILI,
            results=results,
            total_results=total_int or len(results),
        )

    # ── 用户搜索（聚合，不抛异常） ──────────────────────────

    async def search_users(
        self,
        keyword: str,
        page: int = 1,
        max_results: int = 20,
    ) -> list[BilibiliSearchUserItem]:
        """搜索用户

        Args:
            keyword: 关键词
            page: 页码
            max_results: 最大返回条数

        Returns:
            BilibiliSearchUserItem 列表，失败返回空列表
        """
        results: list[BilibiliSearchUserItem] = []
        try:
            params: dict[str, Any] = {
                "search_type": "bili_user",
                "keyword": keyword,
                "page": page,
            }
            payload = await self._wbi_get("/x/web-interface/search/type", params)
            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 用户搜索返回错误 code=%s msg=%s",
                    code,
                    payload.get("message"),
                )
                return []

            data = payload.get("data") or {}
            items = data.get("result") or []
            if not isinstance(items, list):
                return []

            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    results.append(
                        BilibiliSearchUserItem(
                            mid=int(item.get("mid", 0) or 0),
                            uname=str(item.get("uname", "") or ""),
                            usign=str(item.get("usign", "") or ""),
                            fans=int(item.get("fans", 0) or 0),
                            videos=int(item.get("videos", 0) or 0),
                            level=int(item.get("level", 0) or 0),
                            upic=str(item.get("upic", "") or ""),
                            official_verify_type=int(
                                (item.get("official_verify") or {}).get("type", -1)
                            ),
                        )
                    )
                    if len(results) >= max_results:
                        break
                except Exception as e:
                    logger.debug("Bilibili 用户结果解析失败: %s", e)
                    continue
        except Exception as e:
            logger.warning("Bilibili 用户搜索失败 (kw=%s): %s", keyword, e)
        return results

    # ── 视频详情（查找，抛异常） ────────────────────────────

    async def get_video_details(self, bvid: str) -> BilibiliVideoDetail:
        """获取视频详情

        Args:
            bvid: 视频 BV 号

        Returns:
            BilibiliVideoDetail

        Raises:
            BilibiliNotFound / BilibiliError
        """
        payload = await self._plain_get("/x/web-interface/view", {"bvid": bvid})
        data = self._check_code(payload)

        owner_data = data.get("owner") or {}
        stat_data = data.get("stat") or {}

        # tags 来自 desc_v2 / 单独的 /x/tag/archive/tags 接口；这里仅尝试从
        # data.tname 之外的 tag 字段提取（兼容字段缺失场景）
        tags_raw = data.get("tags") or data.get("tag") or []
        tags: list[str] = []
        if isinstance(tags_raw, list):
            for t in tags_raw:
                if isinstance(t, dict):
                    name = t.get("tag_name") or t.get("name")
                    if name:
                        tags.append(str(name))
                elif isinstance(t, str):
                    tags.append(t)
        elif isinstance(tags_raw, str):
            tags = [s.strip() for s in tags_raw.split(",") if s.strip()]

        return BilibiliVideoDetail(
            bvid=str(data.get("bvid", "") or ""),
            aid=int(data.get("aid", 0) or 0),
            cid=int(data.get("cid", 0) or 0),
            title=str(data.get("title", "") or ""),
            description=str(data.get("desc", "") or ""),
            pic=str(data.get("pic", "") or ""),
            duration=int(data.get("duration", 0) or 0),
            pubdate=int(data.get("pubdate", 0) or 0),
            ctime=int(data.get("ctime", 0) or 0),
            owner=VideoOwner(**owner_data) if isinstance(owner_data, dict) else VideoOwner(),
            stat=VideoStat(**stat_data) if isinstance(stat_data, dict) else VideoStat(),
            tname=str(data.get("tname", "") or ""),
            dynamic=str(data.get("dynamic", "") or ""),
            tags=tags,
        )

    # ── 专栏文章搜索（聚合，不抛异常） ──────────────────────

    async def search_articles(
        self,
        keyword: str,
        *,
        page: int = 1,
        max_results: int = 20,
    ) -> list[BilibiliArticleResult]:
        """搜索 Bilibili 专栏文章。

        使用 /x/web-interface/search/type 接口，search_type=article。

        Args:
            keyword: 搜索关键词
            page: 页码（从 1 开始）
            max_results: 最大返回条数（B 站单页上限 50）

        Returns:
            BilibiliArticleResult 列表；失败时返回空列表（与其他搜索方法一致的软失败语义）
        """
        params = {
            "keyword": keyword,
            "search_type": "article",
            "page": str(page),
            "page_size": str(min(max_results, self._MAX_PAGE_SIZE)),
        }
        try:
            payload = await self._wbi_get(
                "/x/web-interface/search/type",
                params=params,
            )
            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 文章搜索返回错误 code=%s msg=%s",
                    code,
                    payload.get("message"),
                )
                return []

            data = payload.get("data") or {}
            items = data.get("result") or []
            if not isinstance(items, list):
                return []

            results: list[BilibiliArticleResult] = []
            for item in items[:max_results]:
                if not isinstance(item, dict):
                    continue
                try:
                    aid = int(item.get("id", 0) or 0)
                    results.append(
                        BilibiliArticleResult(
                            id=aid,
                            title=re.sub(r"<[^>]+>", "", str(item.get("title", "") or "")),
                            author=str(item.get("author", "") or ""),
                            mid=int(item.get("mid", 0) or 0),
                            category_name=str(item.get("category_name", "") or ""),
                            desc=str(item.get("desc", "") or ""),
                            view=int(item.get("view", 0) or 0),
                            like=int(item.get("like", 0) or 0),
                            reply=int(item.get("reply", 0) or 0),
                            pub_date=int(item.get("pub_date", 0) or 0),
                            url=f"https://www.bilibili.com/read/cv{aid}" if aid else "",
                            image_urls=[u for u in (item.get("image_urls") or []) if u],
                        )
                    )
                except Exception as e:
                    logger.debug("Bilibili 文章条目解析失败: %s", e)
                    continue
            return results
        except Exception as e:
            logger.debug("bilibili article search failed for %r: %s", keyword, e, exc_info=True)
            return []
