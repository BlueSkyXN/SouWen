"""Bilibili 视频搜索客户端

文件用途：
    B 站（bilibili.com）公开搜索 API 客户端。通过 B 站 Web 端搜索接口
    检索视频内容，无需 API Key 或登录。返回结果统一映射为 SouWen 的
    WebSearchResult 模型，便于与其它 Web 数据源聚合。

    同时实现了 WBI 签名（复现自 bilibili-mcp-server 项目的 TypeScript 原始代码），
    用于访问需要鉴权的用户信息、视频详情等接口。

    虽然 B 站接口返回的是 JSON（不是 HTML），但本客户端仍继承
    BaseScraper —— 目的是复用其 TLS 指纹伪装（curl_cffi impersonate）、
    浏览器级请求头、自适应限速与自动重试能力，避免被风控。

函数/类清单：
    BilibiliClient（类）
        - 功能：B 站视频搜索 + 用户/视频信息客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "bilibili",
                  BASE_URL = "https://api.bilibili.com",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：
            search(query, max_results, order) -> WebSearchResponse
            get_user_info(mid) -> dict
            get_video_detail(bvid) -> dict
            get_related_videos(bvid) -> list[dict]

    BilibiliClient.__init__(**kwargs)
        - 功能：初始化客户端，转发参数给 BaseScraper；初始化 WBI 密钥缓存

    BilibiliClient.search(query, max_results=20, order="totalrank")
            -> WebSearchResponse
        - 功能：调用 /x/web-interface/search/type 检索视频结果
        - 输入：
            query 关键词；
            max_results 最多返回条数（B 站单页上限 50，超过会被截断）；
            order 排序方式：
                "totalrank" 综合排序（默认）
                "click"     播放量
                "pubdate"   最新发布
                "dm"        弹幕数
                "stow"      收藏数
        - 输出：WebSearchResponse，results 元素为 WebSearchResult
        - 异常：HTTP/JSON/解析异常被捕获并降级为返回空结果集

    BilibiliClient._clean_html(text) -> str
        - 功能：去除 B 站搜索结果 title 字段中的 HTML 高亮标签
                （如 <em class="keyword">…</em>）

    BilibiliClient._get_wbi_keys() -> tuple[str, str]
        - 功能：从 /x/web-interface/nav 获取 WBI 签名所需的 img_key 和 sub_key
        - 带 1 小时 TTL 内存缓存，避免频繁请求 nav 端点
        - 参考：bilibili-mcp-server/src/common/wbi.ts getWbiKeys()

    BilibiliClient._build_wbi_signed_url(endpoint, params) -> str
        - 功能：对参数进行 WBI 签名，返回完整的签名 URL
        - 实现了 bilibili-mcp-server 中的 getMixinKey() + encWbi() 逻辑

    BilibiliClient.get_user_info(mid) -> dict
        - 功能：获取 B 站用户信息（用户名、粉丝数、等级、签名等）
        - 端点：/x/space/wbi/acc/info（需 WBI 签名）+
               /x/relation/stat（粉丝/关注数，无需签名）
        - 返回：用户信息字典，字段包含 mid, name, face, sign, level,
               birthday, tags, official, follower, following, live_room

    BilibiliClient.get_video_detail(bvid) -> dict
        - 功能：获取视频详情（标题、简介、UP 主、统计数据等）
        - 端点：/x/web-interface/view（需传 bvid 参数，无需 WBI 签名）
        - 返回：视频信息字典，字段包含 bvid, aid, title, desc, pic,
               owner, stat(view/danmaku/reply/favorite/coin/share/like),
               duration, pubdate

    BilibiliClient.get_related_videos(bvid) -> list[dict]
        - 功能：获取视频相关推荐列表
        - 端点：/x/web-interface/related/recommend
        - 返回：相关视频列表，每项含 bvid, aid, title, pic, owner, stat, duration

模块依赖：
    - hashlib：MD5 计算（WBI 签名）
    - logging：日志
    - re：HTML 标签清理
    - time：WBI 签名时间戳
    - urllib.parse.quote_plus：关键词 URL 编码
    - souwen.models：SourceType / WebSearchResult / WebSearchResponse
    - souwen.scraper.base：BaseScraper

技术要点：
    - 必须携带 Referer: https://www.bilibili.com，否则 API 返回 -412 风控
    - title 字段含 <em class="keyword"> 高亮标签，需要清理
    - description / snippet 截断到 300 字符以控制载荷大小
    - source 字段使用 SourceType.WEB_BILIBILI 枚举值
    - WBI 签名：混合密钥编码表重排 → MD5(sorted_params + mixin_key) = w_rid
    - WBI 密钥从 /x/web-interface/nav 获取，缓存 1 小时（_WBI_KEY_TTL）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus, quote

from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.bilibili")

# WBI 签名混合密钥编码表（64 个索引），来源：
# https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
# ⚠️ 此表由 B 站客户端规定，不可修改——任何变动都会导致签名验证失败。
_MIXIN_KEY_ENC_TAB: tuple[int, ...] = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)

# WBI 密钥缓存有效期（秒）
_WBI_KEY_TTL = 3600


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    """从 img_key + sub_key 生成 WBI 混合密钥

    按 _MIXIN_KEY_ENC_TAB 重排字符后取前 32 位。
    对应 bilibili-mcp-server 中的 getMixinKey()。

    Args:
        img_key: 从 nav 端点获取的 img_url 文件名
        sub_key: 从 nav 端点获取的 sub_url 文件名

    Returns:
        32 字符的混合密钥
    """
    orig = img_key + sub_key
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB if i < len(orig))[:32]


def _sign_wbi_params(params: dict[str, Any], img_key: str, sub_key: str) -> str:
    """对请求参数进行 WBI 签名，返回带签名的查询字符串

    对应 bilibili-mcp-server 中的 encWbi()。
    步骤：
    1. 拼接 wts（当前时间戳）
    2. 按 key 排序，过滤值中的 !'()* 特殊字符
    3. 计算 MD5(sorted_query + mixin_key) = w_rid

    Args:
        params: 请求参数字典
        img_key: WBI img_key
        sub_key: WBI sub_key

    Returns:
        带 w_rid 和 wts 的 URL 查询字符串
    """
    mixin_key = _get_mixin_key(img_key, sub_key)
    wts = int(time.time())

    sign_params = dict(params)
    sign_params["wts"] = wts

    # 过滤值中的特殊字符，按 key 排序
    _FILTER_RE = re.compile(r"[!'()*]")
    query = "&".join(
        f"{quote(str(k), safe='')}"
        f"={quote(_FILTER_RE.sub('', str(v)), safe='')}"
        for k, v in sorted(sign_params.items())
    )

    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return f"{query}&w_rid={w_rid}"


class BilibiliClient(BaseScraper):
    """Bilibili 视频搜索 + 用户/视频信息客户端

    通过 B 站公开 Web 搜索 API 检索视频，并支持通过 WBI 签名访问
    用户信息、视频详情等需要鉴权的接口。无需 API Key 或账号登录。

    继承 BaseScraper 是为了复用 TLS 指纹模拟、浏览器请求头、
    自适应礼貌延迟与自动重试，降低被风控的概率。

    WBI 签名实现参考：
        https://github.com/wangshunnn/bilibili-mcp-server（TypeScript → Python 移植）

    Attributes:
        ENGINE_NAME: 引擎标识 "bilibili"
        BASE_URL:    API 基础地址 https://api.bilibili.com
    """

    ENGINE_NAME = "bilibili"
    BASE_URL = "https://api.bilibili.com"

    # B 站单页结果上限
    _MAX_PAGE_SIZE = 50
    # snippet 截断长度，避免载荷过大
    _SNIPPET_MAX_LEN = 300

    def __init__(self, **kwargs: Any) -> None:
        # 礼貌延迟 1~3 秒、最多重试 3 次；其余参数透传到 BaseScraper
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)
        # WBI 密钥缓存：(img_key, sub_key, timestamp)
        self._wbi_cache: tuple[str, str, float] | None = None
        # 防止并发请求同时刷新 WBI 密钥（asyncio.Lock 懒加载，避免绑定错误的 event loop）
        self._wbi_lock: asyncio.Lock | None = None

    @staticmethod
    def _clean_html(text: str) -> str:
        """清理 HTML 标签

        B 站搜索结果 title 字段中关键词会被 <em class="keyword">…</em>
        包裹用于前端高亮，本方法将所有 HTML 标签去除并 strip 空白。

        Args:
            text: 含 HTML 标签的原始文本

        Returns:
            去除标签后的纯文本；输入为空/None 时返回空串
        """
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    async def _get_wbi_keys(self) -> tuple[str, str]:
        """获取 WBI 签名密钥（带 1 小时 TTL 缓存）

        从 /x/web-interface/nav 端点获取 img_url 和 sub_url，
        从 URL 路径中提取文件名作为 img_key 和 sub_key。

        对应 bilibili-mcp-server 中的 getWbiKeys()。
        无需登录或 SESSDATA Cookie 即可访问此端点。

        Returns:
            (img_key, sub_key) 元组

        Raises:
            RuntimeError: 获取或解析 WBI 密钥失败
        """
        now = time.time()
        # 快速路径：缓存有效，直接返回（无锁开销）
        if self._wbi_cache is not None:
            img_key, sub_key, cached_at = self._wbi_cache
            if now - cached_at < _WBI_KEY_TTL:
                return img_key, sub_key

        # 懒加载 asyncio.Lock，避免在 __init__ 时绑定错误的 event loop
        if self._wbi_lock is None:
            self._wbi_lock = asyncio.Lock()

        async with self._wbi_lock:
            # 二次检查：另一个协程可能已刷新缓存
            now = time.time()
            if self._wbi_cache is not None:
                img_key, sub_key, cached_at = self._wbi_cache
                if now - cached_at < _WBI_KEY_TTL:
                    return img_key, sub_key

            nav_url = f"{self._resolved_base_url}/x/web-interface/nav"
            headers = {
                "Referer": "https://www.bilibili.com",
                "Origin": "https://www.bilibili.com",
            }

            try:
                resp = await self._fetch(nav_url, headers=headers)
                data = resp.json()
            except Exception as e:
                raise RuntimeError(f"获取 WBI 密钥失败: {e}") from e

            try:
                wbi_img = data["data"]["wbi_img"]
                img_url: str = wbi_img["img_url"]
                sub_url: str = wbi_img["sub_url"]
                # 从 URL 中提取文件名（去扩展名）
                img_key = img_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                sub_key = sub_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            except (KeyError, IndexError, AttributeError) as e:
                raise RuntimeError(
                    f"WBI 密钥解析失败（字段 '{e}'），"
                    f"data.wbi_img 结构：{data.get('data', {}).get('wbi_img')}"
                ) from e

            self._wbi_cache = (img_key, sub_key, now)
            logger.debug("WBI 密钥已更新: img_key=%s sub_key=%s", img_key[:8], sub_key[:8])
            return img_key, sub_key

    async def _build_wbi_signed_url(self, endpoint: str, params: dict[str, Any]) -> str:
        """构造带 WBI 签名的完整 URL

        Args:
            endpoint: API 路径（如 "/x/space/wbi/acc/info"）
            params: 请求参数字典

        Returns:
            完整的带签名查询字符串的 URL
        """
        img_key, sub_key = await self._get_wbi_keys()
        signed_query = _sign_wbi_params(params, img_key, sub_key)
        return f"{self._resolved_base_url}{endpoint}?{signed_query}"

    async def _api_get(self, url: str, headers: dict[str, str] | None = None) -> dict:
        """发起 API 请求并解析 JSON，统一处理错误码

        Args:
            url: 完整请求 URL
            headers: 额外请求头

        Returns:
            响应的 data 字段（dict）

        Raises:
            RuntimeError: 网络错误、JSON 解析失败或 API 返回非零错误码
        """
        _headers = {
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            _headers.update(headers)

        try:
            resp = await self._fetch(url, headers=_headers)
            payload = resp.json()
        except Exception as e:
            raise RuntimeError(f"请求失败: {e}") from e

        code = payload.get("code")
        if code != 0:
            msg = payload.get("message", "未知错误")
            raise RuntimeError(f"API 返回错误 code={code}: {msg}")

        return payload.get("data") or {}

    async def get_user_info(self, mid: int) -> dict:
        """获取 B 站用户信息

        聚合用户基本信息（/x/space/wbi/acc/info）与关注粉丝数
        （/x/relation/stat），对应 bilibili-mcp-server 的 getUserInfo()。

        /x/space/wbi/acc/info 端点需要 WBI 签名；
        /x/relation/stat 端点无需签名。

        Args:
            mid: 用户数字 ID

        Returns:
            用户信息字典，包含字段：
                mid, name, face, sign, level, birthday, tags,
                official (role/title/desc), live_room (url/liveStatus),
                follower, following

        Raises:
            RuntimeError: 请求失败或 API 返回错误时抛出
        """
        # 获取用户基本信息（需 WBI 签名）
        info_url = await self._build_wbi_signed_url(
            "/x/space/wbi/acc/info", {"mid": mid}
        )
        user_data = await self._api_get(info_url)

        # 获取粉丝/关注数（无需 WBI 签名）
        stat_url = (
            f"{self._resolved_base_url}/x/relation/stat?vmid={mid}"
        )
        try:
            stat_data = await self._api_get(stat_url)
            user_data["follower"] = stat_data.get("follower")
            user_data["following"] = stat_data.get("following")
        except Exception as e:
            logger.warning("获取用户关注/粉丝数失败 (mid=%s): %s", mid, e)
            user_data["follower"] = None
            user_data["following"] = None

        logger.info("Bilibili 用户信息获取成功 (mid=%s name=%s)", mid, user_data.get("name"))
        return user_data

    async def get_video_detail(self, bvid: str) -> dict:
        """获取 B 站视频详情

        对应 bilibili-mcp-server 的 getVideoDetail()。
        端点 /x/web-interface/view 无需 WBI 签名。

        Args:
            bvid: 视频 BVID，如 "BV1xx411c7mD"

        Returns:
            视频信息字典，包含字段：
                bvid, aid, title, desc, pic, owner (mid/name/face),
                stat (view/danmaku/reply/favorite/coin/share/like),
                duration, pubdate, ctime, cid, tags

        Raises:
            RuntimeError: 请求失败或 API 返回错误时抛出
        """
        url = f"{self._resolved_base_url}/x/web-interface/view?bvid={quote_plus(bvid)}"
        data = await self._api_get(url)
        logger.info("Bilibili 视频详情获取成功 (bvid=%s title=%s)", bvid, data.get("title"))
        return data

    async def get_related_videos(self, bvid: str) -> list[dict]:
        """获取 B 站视频相关推荐列表

        对应 bilibili-mcp-server 的 getRelatedVideos()。
        端点 /x/web-interface/related/recommend 无需 WBI 签名。

        Args:
            bvid: 视频 BVID，如 "BV1xx411c7mD"

        Returns:
            相关视频列表，每项包含：
                bvid, aid, title, pic, owner (mid/name), stat (view/danmaku), duration

        Raises:
            RuntimeError: 请求失败或 API 返回错误时抛出
        """
        url = (
            f"{self._resolved_base_url}/x/web-interface/related/recommend"
            f"?bvid={quote_plus(bvid)}"
        )
        data = await self._api_get(url)
        # API 返回 list 直接在 data 字段
        if isinstance(data, list):
            logger.info("Bilibili 相关视频获取成功 (bvid=%s count=%d)", bvid, len(data))
            return data
        # 部分端点封装在 list 子字段
        result = data.get("list") or data.get("result") or []
        logger.info("Bilibili 相关视频获取成功 (bvid=%s count=%d)", bvid, len(result))
        return result

    async def search(
        self,
        query: str,
        max_results: int = 20,
        order: str = "totalrank",
    ) -> WebSearchResponse:
        """搜索 B 站视频

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（上限 50，超过被截断）
            order: 排序方式，可选
                "totalrank" 综合（默认）/ "click" 播放量 /
                "pubdate" 最新 / "dm" 弹幕数 / "stow" 收藏数

        Returns:
            WebSearchResponse，results 为 WebSearchResult 列表
        """
        page_size = max(1, min(int(max_results), self._MAX_PAGE_SIZE))
        url = (
            f"{self._resolved_base_url}/x/web-interface/search/type"
            f"?search_type=video&keyword={quote_plus(query)}"
            f"&page=1&page_size={page_size}&order={order}"
        )

        # B 站对 Referer 强校验，缺失则返回 -412 风控
        headers = {
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

        results: list[WebSearchResult] = []

        try:
            resp = await self._fetch(url, headers=headers)
        except Exception as e:  # 网络异常 → 降级为空结果，不打断聚合
            logger.warning("Bilibili 请求失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        try:
            payload = resp.json()
        except Exception as e:
            logger.warning("Bilibili JSON 解析失败 (query=%s): %s", query, e)
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        code = payload.get("code")
        if code != 0:
            # 常见：-412 风控、-101 未登录、-110 未授权
            logger.warning(
                "Bilibili API 返回错误 code=%s message=%s (query=%s)",
                code,
                payload.get("message"),
                query,
            )
            return WebSearchResponse(
                query=query,
                source=SourceType.WEB_BILIBILI,
                results=results,
                total_results=0,
            )

        data = payload.get("data") or {}
        items = data.get("result") or []
        if not isinstance(items, list):
            # /search/all/v2 端点的 data.result 是分组数组，这里兜底
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                title = self._clean_html(item.get("title", ""))
                arcurl = item.get("arcurl") or ""
                if not title or not arcurl:
                    continue

                description = (item.get("description") or "")[: self._SNIPPET_MAX_LEN]

                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_BILIBILI,
                        title=title,
                        url=str(arcurl),
                        snippet=description,
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

        logger.info("Bilibili 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BILIBILI,
            results=results,
            total_results=total_int,
        )
