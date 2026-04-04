"""浏览器指纹管理

提供真实浏览器请求头和 TLS 指纹模拟，
用于突破反爬检测（JA3 指纹、User-Agent、Sec-CH-UA 等）。
"""

from __future__ import annotations

import random

# Chrome 浏览器指纹库（定期更新）
_CHROME_VERSIONS = [
    {
        "version": "146",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "impersonate": "chrome124",  # curl_cffi 最高仅支持 chrome124 的 TLS 指纹，UA 用新版无碍
    },
    {
        "version": "125",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="125", "Not-A.Brand";v="24", "Google Chrome";v="125"',
        "impersonate": "chrome120",
    },
    {
        "version": "124",
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="124", "Not-A.Brand";v="24", "Google Chrome";v="124"',
        "impersonate": "chrome120",
    },
]

# 操作系统指纹（与 Chrome 版本随机组合，增加指纹多样性）
_PLATFORMS = [
    {"platform": '"Windows"', "ua_os": "Windows NT 10.0; Win64; x64"},
    {"platform": '"macOS"', "ua_os": "Macintosh; Intel Mac OS X 10_15_7"},
    {"platform": '"Linux"', "ua_os": "X11; Linux x86_64"},
]


class BrowserFingerprint:
    """浏览器指纹生成器

    生成一致的浏览器指纹（UA + Sec-CH-UA + TLS impersonate），
    确保请求在网络层和应用层看起来像真实浏览器。
    """

    def __init__(self, chrome_version: dict | None = None):
        self._chrome = chrome_version or random.choice(_CHROME_VERSIONS)
        self._platform = random.choice(_PLATFORMS)

    @property
    def user_agent(self) -> str:
        """完整 User-Agent 字符串"""
        return self._chrome["ua"]

    @property
    def impersonate(self) -> str:
        """curl_cffi impersonate 参数（TLS 指纹模拟）"""
        return self._chrome["impersonate"]

    @property
    def headers(self) -> dict[str, str]:
        """完整的浏览器请求头（含 Sec-CH-UA 系列）"""
        return {
            "User-Agent": self._chrome["ua"],
            "sec-ch-ua": self._chrome["sec_ch_ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self._platform["platform"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def rotate(self) -> "BrowserFingerprint":
        """轮换到新的指纹（保持一致性）"""
        return BrowserFingerprint()


def get_default_fingerprint() -> BrowserFingerprint:
    """获取默认浏览器指纹"""
    return BrowserFingerprint(_CHROME_VERSIONS[0])


def get_random_fingerprint() -> BrowserFingerprint:
    """获取随机浏览器指纹"""
    return BrowserFingerprint()


def get_api_headers(
    email: str | None = None,
    api_key: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, str]:
    """获取 API 请求头（非爬虫场景，使用规范的 UA）

    API 场景不需要伪装浏览器，使用标准 SouWen UA + 可选 polite 参数。
    """
    headers: dict[str, str] = {
        "User-Agent": "SouWen/0.1.0 (Academic & Patent Search; https://github.com/souwen)",
    }
    if email:
        headers["From"] = email
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers
