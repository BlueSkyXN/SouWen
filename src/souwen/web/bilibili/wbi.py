"""Bilibili WBI 签名模块

实现 Bilibili Web API 所需的 WBI（Web-Interface）参数签名机制。
WBI 签名用于 /x/space/wbi/* 和部分搜索接口的反爬校验。

算法来源：
    - SocialSisterYi/bilibili-API-collect（社区逆向文档）
    - wangshunnn/bilibili-mcp-server（TypeScript 实现参考）
    - BlueSkyXN/bili-cli（Go 实现参考，含 1 小时缓存策略）

签名流程：
    1. 从 /x/web-interface/nav 获取 wbi_img.img_url 和 sub_url
    2. 提取 img_key 和 sub_key（URL 路径中的文件名去掉扩展名）
    3. 拼接 img_key + sub_key，通过固定置换表重排取前 32 字符 → mixin_key
    4. 将请求参数加上 wts（Unix 时间戳），按 key 排序后 URL 编码
    5. 计算 md5(encoded_params + mixin_key) → w_rid
    6. 将 wts 和 w_rid 追加到原参数中

技术要点：
    - 使用 asyncio.Lock 防止并发请求时 WBI key 被重复获取（thundering herd）
    - 默认 1 小时缓存 TTL，-403/-352 触发强制刷新
    - 参数值中 !'()* 字符需过滤（Bilibili 服务端特殊要求）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any
from urllib.parse import quote

logger = logging.getLogger("souwen.web.bilibili.wbi")

# WBI 签名固定置换表（64 位索引），用于从 img_key+sub_key 生成 mixin_key
# 来源：Bilibili 前端 JS 逆向 / bilibili-API-collect 文档
MIXIN_KEY_ENC_TAB: list[int] = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# WBI key 缓存 TTL（秒）
_WBI_CACHE_TTL = 3600  # 1 小时

# 需要从参数值中过滤的字符（Bilibili 服务端要求）
_FILTER_CHARS_RE = re.compile(r"[!'()*]")


def get_mixin_key(img_key: str, sub_key: str) -> str:
    """根据 img_key 和 sub_key 通过置换表生成 32 字节 mixin_key

    Args:
        img_key: 从 wbi_img.img_url 提取的 key
        sub_key: 从 wbi_img.sub_url 提取的 key

    Returns:
        32 字符的 mixin_key 字符串
    """
    orig = img_key + sub_key
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB if i < len(orig))[:32]


def _extract_key_from_url(url: str) -> str:
    """从 WBI URL 中提取 key（文件名去掉扩展名）

    例如 https://i0.hdslb.com/bfs/wbi/xxx.png → xxx

    Args:
        url: wbi_img 的 img_url 或 sub_url

    Returns:
        key 字符串
    """
    # 取最后一个 / 之后的部分
    filename = url.rsplit("/", 1)[-1]
    # 去掉扩展名
    return filename.rsplit(".", 1)[0]


def sign_params(
    params: dict[str, Any],
    img_key: str,
    sub_key: str,
    ts: int | None = None,
) -> dict[str, str]:
    """对请求参数进行 WBI 签名

    Args:
        params: 原始请求参数
        img_key: WBI img key
        sub_key: WBI sub key
        ts: Unix 时间戳（秒），默认当前时间

    Returns:
        签名后的参数字典（包含 wts 和 w_rid）
    """
    mixin_key = get_mixin_key(img_key, sub_key)
    if ts is None:
        ts = int(time.time())

    # 复制参数并添加时间戳
    signed = {k: str(v) for k, v in params.items()}
    signed["wts"] = str(ts)

    # 按 key 排序，过滤特殊字符，URL 编码
    sorted_keys = sorted(signed.keys())
    parts = []
    for key in sorted_keys:
        value = _FILTER_CHARS_RE.sub("", signed[key])
        parts.append(f"{quote(key, safe='')}={quote(value, safe='')}")
    query = "&".join(parts)

    # 计算 w_rid = md5(query + mixin_key)
    w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    signed["w_rid"] = w_rid

    return signed


class WbiSigner:
    """WBI 签名器（含 key 缓存和并发安全）

    使用示例::

        signer = WbiSigner()
        signed_params = await signer.sign(fetch_fn, {"mid": "12345"})

    其中 fetch_fn 是一个异步函数，接受 URL 返回 httpx.Response。
    """

    def __init__(self, cache_ttl: int = _WBI_CACHE_TTL) -> None:
        self._img_key: str | None = None
        self._sub_key: str | None = None
        self._fetched_at: float = 0.0
        self._cache_ttl = cache_ttl
        self._lock = asyncio.Lock()

    @property
    def has_valid_cache(self) -> bool:
        """缓存是否在有效期内"""
        if self._img_key is None or self._sub_key is None:
            return False
        return (time.time() - self._fetched_at) < self._cache_ttl

    def invalidate(self) -> None:
        """强制使缓存失效（如遇到 -403/-352 时调用）"""
        self._img_key = None
        self._sub_key = None
        self._fetched_at = 0.0
        logger.debug("WBI key 缓存已失效")

    async def _fetch_keys(self, fetch_fn) -> tuple[str, str]:
        """从 /x/web-interface/nav 获取 WBI key

        Args:
            fetch_fn: 异步 HTTP 请求函数，签名 (url, headers) -> Response

        Returns:
            (img_key, sub_key) 元组

        Raises:
            ValueError: 响应中缺少 wbi_img 数据
        """
        url = "https://api.bilibili.com/x/web-interface/nav"
        headers = {
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
        }

        resp = await fetch_fn(url, headers=headers)
        data = resp.json()

        if data.get("code") != 0:
            logger.warning("获取 WBI key 失败: code=%s msg=%s", data.get("code"), data.get("message"))

        # 即使 code != 0（如 -101 未登录），data.wbi_img 通常仍然存在
        wbi_img = (data.get("data") or {}).get("wbi_img") or {}
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        if not img_url or not sub_url:
            raise ValueError(f"WBI key 响应缺少 img_url/sub_url: {wbi_img}")

        img_key = _extract_key_from_url(img_url)
        sub_key = _extract_key_from_url(sub_url)
        logger.debug("获取 WBI keys: img=%s sub=%s", img_key[:8] + "...", sub_key[:8] + "...")
        return img_key, sub_key

    async def ensure_keys(self, fetch_fn) -> tuple[str, str]:
        """确保 WBI key 已加载（带并发锁）

        Args:
            fetch_fn: 异步 HTTP 请求函数

        Returns:
            (img_key, sub_key)
        """
        if self.has_valid_cache:
            return self._img_key, self._sub_key  # type: ignore[return-value]

        async with self._lock:
            # double-check after acquiring lock
            if self.has_valid_cache:
                return self._img_key, self._sub_key  # type: ignore[return-value]

            self._img_key, self._sub_key = await self._fetch_keys(fetch_fn)
            self._fetched_at = time.time()
            return self._img_key, self._sub_key

    async def sign(
        self,
        fetch_fn,
        params: dict[str, Any],
        ts: int | None = None,
    ) -> dict[str, str]:
        """签名请求参数（自动获取/缓存 WBI key）

        Args:
            fetch_fn: 异步 HTTP 请求函数
            params: 原始请求参数
            ts: 可选 Unix 时间戳

        Returns:
            签名后的参数字典
        """
        img_key, sub_key = await self.ensure_keys(fetch_fn)
        return sign_params(params, img_key, sub_key, ts=ts)
