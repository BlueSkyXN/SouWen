"""Bilibili 全功能客户端

文件用途：
    B 站（bilibili.com）Web API 的 Python 客户端，覆盖以下能力：
        - 视频搜索（WBI 签名，向后兼容旧 BilibiliClient.search 接口）
        - 视频详情 / 用户信息 / 评论 / 字幕 / AI 摘要
        - 用户视频列表 / 热门 / 排行榜 / 相关推荐 / 用户搜索

    继承 BaseScraper 复用 TLS 指纹模拟、浏览器请求头、自适应限速
    与自动重试能力，降低被风控的概率。

设计约定：
    - 聚合方法（search / search_users / get_popular / get_ranking /
      get_related）：失败降级为空结果，不抛异常，便于参与多源聚合。
    - 查找方法（get_video_details / get_user_info / get_user_videos /
      get_comments / get_subtitles / get_ai_summary）：失败抛
      _errors.py 中定义的强类型异常，由调用方决定如何处理。

函数/类清单：
    BilibiliClient（类）— 主客户端
        ENGINE_NAME = "bilibili"
        BASE_URL    = "https://api.bilibili.com"

        # 基础工具
        _build_headers() -> dict[str, str]
        _wbi_sign(params) -> dict[str, str]
        _wbi_get(path, params, *, retry_on_risk=True) -> dict
        _plain_get(path, params=None) -> dict
        _check_code(payload) -> dict           # 抛异常或返回 data
        _clean_html(text) -> str               # 兼容旧实现

        # 聚合（不抛异常）
        search(query, max_results=20, order="totalrank") -> WebSearchResponse
        search_users(keyword, page=1, max_results=20) -> list[BilibiliSearchUserItem]
        get_popular(page=1, page_size=20) -> list[BilibiliPopularVideo]
        get_ranking(rid=0, type="all") -> list[BilibiliRankVideo]
        get_related(bvid) -> list[BilibiliRelatedVideo]

        # 查找（抛异常）
        get_video_details(bvid) -> BilibiliVideoDetail
        get_user_info(mid) -> BilibiliUserInfo
        get_user_videos(mid, page=1, page_size=30)
            -> tuple[list[BilibiliUserVideoItem], int]
        get_comments(bvid, sort=1, page=1, max_comments=50) -> list[BilibiliComment]
        get_subtitles(bvid) -> list[BilibiliSubtitle]
        get_ai_summary(bvid) -> BilibiliAISummary

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
    - 字幕需要两次请求：先 view 拿 aid+cid，再 player/wbi/v2 拿
      subtitle_url，最后 GET 字幕 JSON 拿 lines；字幕 URL 常以 //
      开头需要补全 https:。
    - AI 摘要在视频未被生成摘要时返回 result_type=0，仅当真错时抛异常。
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
    BilibiliAISummary,
    BilibiliComment,
    BilibiliPopularVideo,
    BilibiliRankVideo,
    BilibiliRelatedVideo,
    BilibiliSearchUserItem,
    BilibiliSubtitle,
    BilibiliSubtitleLine,
    BilibiliUserInfo,
    BilibiliUserVideoItem,
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

    # ── 用户信息（查找，抛异常） ────────────────────────────

    async def get_user_info(self, mid: int) -> BilibiliUserInfo:
        """获取用户信息（合并 acc/info + relation/stat）

        Args:
            mid: 用户 UID

        Returns:
            BilibiliUserInfo

        Raises:
            BilibiliNotFound / BilibiliError
        """
        # 1) /x/space/wbi/acc/info — 主信息（WBI）
        info_payload = await self._wbi_get("/x/space/wbi/acc/info", {"mid": int(mid)})
        info = self._check_code(info_payload)

        # 2) /x/relation/stat — 关注/粉丝（无需 WBI）
        following = 0
        follower = 0
        try:
            stat_payload = await self._plain_get("/x/relation/stat", {"vmid": int(mid)})
            stat = self._check_code(stat_payload)
            following = int(stat.get("following", 0) or 0)
            follower = int(stat.get("follower", 0) or 0)
        except Exception as e:
            # 关注/粉丝拉取失败不影响主信息返回
            logger.warning("Bilibili relation/stat 失败 mid=%s: %s", mid, e)

        # 3) /x/space/navnum — 投稿数（best-effort）
        archive_count = 0
        try:
            nav_payload = await self._plain_get("/x/space/navnum", {"mid": int(mid)})
            nav = self._check_code(nav_payload)
            archive_count = int(nav.get("video", 0) or 0)
        except Exception as e:
            logger.debug("Bilibili navnum 失败 mid=%s: %s", mid, e)

        vip_data = info.get("vip") or {}
        official_data = info.get("official") or {}
        live_data = info.get("live_room") or {}

        return BilibiliUserInfo(
            mid=int(info.get("mid", mid) or mid),
            name=str(info.get("name", "") or ""),
            face=str(info.get("face", "") or ""),
            sign=str(info.get("sign", "") or ""),
            level=int(info.get("level", 0) or 0),
            sex=str(info.get("sex", "") or ""),
            birthday=str(info.get("birthday", "") or ""),
            coins=float(info.get("coins", 0) or 0),
            following=following,
            follower=follower,
            archive_count=archive_count,
            vip=vip_data if isinstance(vip_data, dict) else {},
            official=official_data if isinstance(official_data, dict) else {},
            live_room_url=str(live_data.get("url", "") or ""),
            live_status=int(live_data.get("liveStatus", 0) or 0),
        )

    # ── 用户视频列表（查找，抛异常） ────────────────────────

    async def get_user_videos(
        self,
        mid: int,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[BilibiliUserVideoItem], int]:
        """获取用户投稿视频列表（WBI）

        Args:
            mid: 用户 UID
            page: 页码（从 1 开始）
            page_size: 每页条数

        Returns:
            (视频列表, 总条数)

        Raises:
            BilibiliNotFound / BilibiliError
        """
        params: dict[str, Any] = {
            "mid": int(mid),
            "pn": int(page),
            "ps": int(page_size),
            "order": "pubdate",
            "tid": 0,
        }
        payload = await self._wbi_get("/x/space/wbi/arc/search", params)
        data = self._check_code(payload)

        items_data = ((data.get("list") or {}).get("vlist")) or []
        page_info = data.get("page") or {}
        total = int(page_info.get("count", 0) or 0)

        items: list[BilibiliUserVideoItem] = []
        if isinstance(items_data, list):
            for v in items_data:
                if not isinstance(v, dict):
                    continue
                try:
                    items.append(
                        BilibiliUserVideoItem(
                            bvid=str(v.get("bvid", "") or ""),
                            aid=int(v.get("aid", 0) or 0),
                            title=str(v.get("title", "") or ""),
                            description=str(v.get("description", "") or ""),
                            pic=str(v.get("pic", "") or ""),
                            length=str(v.get("length", "") or ""),
                            play=int(v.get("play", 0) or 0),
                            comment=int(v.get("comment", 0) or 0),
                            created=int(v.get("created", 0) or 0),
                        )
                    )
                except Exception as e:
                    logger.debug("Bilibili 用户视频条目解析失败: %s", e)
                    continue
        return items, total

    # ── 评论（查找，抛异常） ────────────────────────────────

    async def get_comments(
        self,
        bvid: str,
        sort: int = 1,
        page: int = 1,
        max_comments: int = 50,
    ) -> list[BilibiliComment]:
        """获取视频评论

        先用 view 接口拿 aid，然后请求 /x/v2/reply。
        硬上限 max_comments 条，可能跨多页累积。

        Args:
            bvid: 视频 BV 号
            sort: 排序 — 0=时间 / 1=点赞 / 2=回复
            page: 起始页码
            max_comments: 最大返回条数

        Returns:
            BilibiliComment 列表

        Raises:
            BilibiliNotFound / BilibiliError
        """
        # 1) 获取 aid
        view_payload = await self._plain_get("/x/web-interface/view", {"bvid": bvid})
        view_data = self._check_code(view_payload)
        aid = int(view_data.get("aid", 0) or 0)
        if aid <= 0:
            raise_for_code(-404, f"无法解析 aid: bvid={bvid}")

        # 2) 翻页拉取评论
        results: list[BilibiliComment] = []
        cur_page = max(1, int(page))
        page_size = 20  # 接口默认页大小
        max_pages = 20  # 硬上限保护，防止极端情况死循环

        for _ in range(max_pages):
            if len(results) >= max_comments:
                break
            params: dict[str, Any] = {
                "oid": aid,
                "type": 1,
                "sort": int(sort),
                "pn": cur_page,
                "ps": page_size,
            }
            payload = await self._plain_get("/x/v2/reply", params)
            data = self._check_code(payload)

            replies = data.get("replies") or []
            if not isinstance(replies, list) or not replies:
                break

            for r in replies:
                if not isinstance(r, dict):
                    continue
                try:
                    member = r.get("member") or {}
                    content = r.get("content") or {}
                    results.append(
                        BilibiliComment(
                            rpid=int(r.get("rpid", 0) or 0),
                            mid=int(r.get("mid", 0) or 0),
                            ctime=int(r.get("ctime", 0) or 0),
                            like=int(r.get("like", 0) or 0),
                            rcount=int(r.get("rcount", 0) or 0),
                            member={
                                "mid": int(member.get("mid", 0) or 0),
                                "uname": str(member.get("uname", "") or ""),
                                "avatar": str(member.get("avatar", "") or ""),
                                "level_info": member.get("level_info") or {},
                            },
                            content={"message": str(content.get("message", "") or "")},
                        )
                    )
                    if len(results) >= max_comments:
                        break
                except Exception as e:
                    logger.debug("Bilibili 评论解析失败: %s", e)
                    continue

            page_info = data.get("page") or {}
            total = int(page_info.get("count", 0) or 0)
            if cur_page * page_size >= total:
                break
            cur_page += 1

        return results[:max_comments]

    # ── 字幕（查找，抛异常） ────────────────────────────────

    async def get_subtitles(self, bvid: str) -> list[BilibiliSubtitle]:
        """获取视频字幕（含字幕行内容）

        流程：
            1. /x/web-interface/view → aid + cid
            2. /x/player/wbi/v2 → subtitle.subtitles[].subtitle_url
            3. GET subtitle_url → body.[]{from, to, content}

        Args:
            bvid: 视频 BV 号

        Returns:
            BilibiliSubtitle 列表（中文优先排前面）

        Raises:
            BilibiliNotFound / BilibiliError
        """
        # 1) 获取 aid + cid
        view_payload = await self._plain_get("/x/web-interface/view", {"bvid": bvid})
        view_data = self._check_code(view_payload)
        aid = int(view_data.get("aid", 0) or 0)
        cid = int(view_data.get("cid", 0) or 0)
        if aid <= 0 or cid <= 0:
            raise_for_code(-404, f"无法解析 aid/cid: bvid={bvid}")

        # 2) 拉取播放器配置（含字幕索引）
        player_payload = await self._wbi_get(
            "/x/player/wbi/v2",
            {"bvid": bvid, "aid": aid, "cid": cid},
        )
        player_data = self._check_code(player_payload)

        subtitle_meta = (player_data.get("subtitle") or {}).get("subtitles") or []
        if not isinstance(subtitle_meta, list) or not subtitle_meta:
            return []

        # 中文优先（zh-* / 中文/中），其余原序
        def _zh_priority(item: dict[str, Any]) -> int:
            lan = str(item.get("lan", "")).lower()
            lan_doc = str(item.get("lan_doc", ""))
            if lan.startswith("zh") or "中" in lan_doc:
                return 0
            return 1

        subtitle_meta = sorted(
            [s for s in subtitle_meta if isinstance(s, dict)],
            key=_zh_priority,
        )

        results: list[BilibiliSubtitle] = []
        for sub in subtitle_meta:
            sub_url = str(sub.get("subtitle_url", "") or "")
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            lines: list[BilibiliSubtitleLine] = []
            if sub_url:
                try:
                    resp = await self._fetch(sub_url, headers=self._build_headers())
                    body = resp.json()
                    if isinstance(body, dict):
                        body_lines = body.get("body") or []
                        if isinstance(body_lines, list):
                            for line in body_lines:
                                if not isinstance(line, dict):
                                    continue
                                try:
                                    lines.append(
                                        BilibiliSubtitleLine(
                                            **{
                                                "from": float(line.get("from", 0) or 0),
                                                "to": float(line.get("to", 0) or 0),
                                                "content": str(line.get("content", "") or ""),
                                                "location": int(line.get("location", 0) or 0),
                                            }
                                        )
                                    )
                                except Exception as e:
                                    logger.debug("字幕行解析失败: %s", e)
                                    continue
                except Exception as e:
                    logger.warning("拉取字幕内容失败 url=%s: %s", sub_url, e)

            results.append(
                BilibiliSubtitle(
                    lan=str(sub.get("lan", "") or ""),
                    lan_doc=str(sub.get("lan_doc", "") or ""),
                    subtitle_url=sub_url,
                    lines=lines,
                )
            )
        return results

    # ── AI 摘要（查找，抛异常） ─────────────────────────────

    async def get_ai_summary(self, bvid: str) -> BilibiliAISummary:
        """获取视频 AI 摘要

        若该视频未生成 AI 摘要，返回 result_type=0 的空摘要而非抛异常。
        仅在接口本身错误（视频不存在等）时抛异常。

        Args:
            bvid: 视频 BV 号

        Returns:
            BilibiliAISummary

        Raises:
            BilibiliNotFound / BilibiliError
        """
        # 1) 获取 aid + cid + up_mid
        view_payload = await self._plain_get("/x/web-interface/view", {"bvid": bvid})
        view_data = self._check_code(view_payload)
        aid = int(view_data.get("aid", 0) or 0)
        cid = int(view_data.get("cid", 0) or 0)
        up_mid = int(((view_data.get("owner") or {}).get("mid", 0)) or 0)
        if aid <= 0 or cid <= 0:
            raise_for_code(-404, f"无法解析 aid/cid: bvid={bvid}")

        # 2) 请求摘要接口（注意：此接口在很多视频上返回 code=0 但 result 为空）
        params: dict[str, Any] = {
            "bvid": bvid,
            "aid": aid,
            "cid": cid,
            "up_mid": up_mid,
        }
        # 此接口实测可走 WBI 也可不走，走 WBI 更安全
        payload = await self._wbi_get(
            "/x/web-interface/view/conclusion/get",
            params,
            retry_on_risk=False,
        )

        code = payload.get("code", 0)
        if code != 0:
            # -101 / -404 等真实错误才抛异常；其他特殊 code 视为无摘要
            if code in (-404, -101, -352, -403, -412, 412, 62002, 62004):
                raise_for_code(int(code), str(payload.get("message", "")))
            logger.info(
                "Bilibili AI 摘要不可用 code=%s msg=%s bvid=%s",
                code,
                payload.get("message"),
                bvid,
            )
            return BilibiliAISummary()

        data = payload.get("data") or {}
        model_result = data.get("model_result") or {}
        result_type = int(model_result.get("result_type", 0) or 0)
        summary = str(model_result.get("summary", "") or "")
        stids_raw = data.get("stid") or data.get("stids") or []
        stids: list[int] = []
        if isinstance(stids_raw, list):
            for s in stids_raw:
                try:
                    stids.append(int(s))
                except (TypeError, ValueError):
                    continue
        return BilibiliAISummary(
            summary=summary,
            stids=stids,
            result_type=result_type,
        )

    # ── 热门（聚合，不抛异常） ──────────────────────────────

    async def get_popular(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BilibiliPopularVideo]:
        """获取当前热门视频列表

        Args:
            page: 页码
            page_size: 每页条数

        Returns:
            BilibiliPopularVideo 列表，失败返回空
        """
        results: list[BilibiliPopularVideo] = []
        try:
            payload = await self._plain_get(
                "/x/web-interface/popular",
                {"pn": int(page), "ps": int(page_size)},
            )
            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 热门返回错误 code=%s msg=%s",
                    code,
                    payload.get("message"),
                )
                return []
            data = payload.get("data") or {}
            items = data.get("list") or []
            if not isinstance(items, list):
                return []
            for v in items:
                if not isinstance(v, dict):
                    continue
                try:
                    owner = v.get("owner") or {}
                    stat = v.get("stat") or {}
                    rcmd_reason = v.get("rcmd_reason") or {}
                    if isinstance(rcmd_reason, dict):
                        rcmd_text = str(rcmd_reason.get("content", "") or "")
                    else:
                        rcmd_text = str(rcmd_reason or "")
                    results.append(
                        BilibiliPopularVideo(
                            bvid=str(v.get("bvid", "") or ""),
                            aid=int(v.get("aid", 0) or 0),
                            title=str(v.get("title", "") or ""),
                            pic=str(v.get("pic", "") or ""),
                            desc=str(v.get("desc", "") or ""),
                            duration=int(v.get("duration", 0) or 0),
                            pubdate=int(v.get("pubdate", 0) or 0),
                            owner=VideoOwner(**owner) if isinstance(owner, dict) else VideoOwner(),
                            stat=VideoStat(**stat) if isinstance(stat, dict) else VideoStat(),
                            rcmd_reason=rcmd_text,
                        )
                    )
                except Exception as e:
                    logger.debug("Bilibili 热门条目解析失败: %s", e)
                    continue
        except Exception as e:
            logger.warning("Bilibili 热门拉取失败: %s", e)
        return results

    # ── 排行榜（聚合，不抛异常） ────────────────────────────

    async def get_ranking(
        self,
        rid: int = 0,
        type: str = "all",
    ) -> list[BilibiliRankVideo]:
        """获取排行榜

        Args:
            rid: 分区 ID（0 表示全站）
            type: 排行榜类型 — all/origin/rookie 等

        Returns:
            BilibiliRankVideo 列表，失败返回空
        """
        results: list[BilibiliRankVideo] = []
        try:
            payload = await self._wbi_get(
                "/x/web-interface/ranking/v2",
                {"rid": int(rid), "type": str(type)},
            )
            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 排行榜返回错误 code=%s msg=%s",
                    code,
                    payload.get("message"),
                )
                return []
            data = payload.get("data") or {}
            items = data.get("list") or []
            if not isinstance(items, list):
                return []
            for idx, v in enumerate(items, start=1):
                if not isinstance(v, dict):
                    continue
                try:
                    owner = v.get("owner") or {}
                    stat = v.get("stat") or {}
                    results.append(
                        BilibiliRankVideo(
                            bvid=str(v.get("bvid", "") or ""),
                            aid=int(v.get("aid", 0) or 0),
                            title=str(v.get("title", "") or ""),
                            pic=str(v.get("pic", "") or ""),
                            desc=str(v.get("desc", "") or ""),
                            duration=int(v.get("duration", 0) or 0),
                            pubdate=int(v.get("pubdate", 0) or 0),
                            owner=VideoOwner(**owner) if isinstance(owner, dict) else VideoOwner(),
                            stat=VideoStat(**stat) if isinstance(stat, dict) else VideoStat(),
                            rank_index=idx,
                            score=int(v.get("score", 0) or 0),
                        )
                    )
                except Exception as e:
                    logger.debug("Bilibili 排行榜条目解析失败: %s", e)
                    continue
        except Exception as e:
            logger.warning("Bilibili 排行榜拉取失败: %s", e)
        return results

    # ── 相关推荐（聚合，不抛异常） ──────────────────────────

    async def get_related(self, bvid: str) -> list[BilibiliRelatedVideo]:
        """获取视频相关推荐

        Args:
            bvid: 视频 BV 号

        Returns:
            BilibiliRelatedVideo 列表，失败返回空
        """
        results: list[BilibiliRelatedVideo] = []
        try:
            payload = await self._plain_get(
                "/x/web-interface/archive/related",
                {"bvid": bvid},
            )
            code = payload.get("code", 0)
            if code != 0:
                logger.warning(
                    "Bilibili 相关推荐返回错误 code=%s msg=%s bvid=%s",
                    code,
                    payload.get("message"),
                    bvid,
                )
                return []
            items = payload.get("data") or []
            if not isinstance(items, list):
                return []
            for v in items:
                if not isinstance(v, dict):
                    continue
                try:
                    owner = v.get("owner") or {}
                    stat = v.get("stat") or {}
                    results.append(
                        BilibiliRelatedVideo(
                            bvid=str(v.get("bvid", "") or ""),
                            aid=int(v.get("aid", 0) or 0),
                            title=str(v.get("title", "") or ""),
                            pic=str(v.get("pic", "") or ""),
                            duration=int(v.get("duration", 0) or 0),
                            pubdate=int(v.get("pubdate", 0) or 0),
                            owner=VideoOwner(**owner) if isinstance(owner, dict) else VideoOwner(),
                            stat=VideoStat(**stat) if isinstance(stat, dict) else VideoStat(),
                        )
                    )
                except Exception as e:
                    logger.debug("Bilibili 相关推荐条目解析失败: %s", e)
                    continue
        except Exception as e:
            logger.warning("Bilibili 相关推荐拉取失败 bvid=%s: %s", bvid, e)
        return results
